#!/bin/zsh
# 用 GLM-5.3 作为执行 Agent 跑 volcengine-ark 的 30 次任务（Claude Code CLI 仅作 harness）
# 用法： GLM_CODING_PLAN_API_KEY=... ./run_agents.sh
set -u
ROOT="${0:A:h}"
: "${GLM_CODING_PLAN_API_KEY:?export GLM_CODING_PLAN_API_KEY first}"

SKILL=/Users/chopinfeng/Workspace/Skillify/volcengine-ark/SKILL.md
SKILLDIR=/Users/chopinfeng/Workspace/Skillify/volcengine-ark

TASK_A='我们在用火山方舟的 Agent Plan（个人版 Medium 套餐），要写一个 main.py，用**Anthropic 协议**那个入口发一次对话请求（问"用一句话介绍 Python"）。这是个成本敏感的场景：套餐里不同模型的抵扣系数差好几倍，所以**必须确保实际服务我的模型就是 doubao-seed-2.0-lite，不能是别的**。脚本跑完请把「我请求的模型」和「服务端实际回给我的模型」都打印出来核对，不一致必须明确报警。API Key 从环境变量 ARK_AGENT_PLAN_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_B='写一个 main.py，用火山方舟 Agent Plan 里的 kimi-k3 模型做情感分类：对"这家店的服务态度太差了，再也不来了"这句话判断情感，只输出「正面」「负面」「中性」三个词之一。我们对成本很敏感，希望把这次调用的输出上限压到 64 token 以内——但前提是**必须真的拿到分类结果**，拿不到就要明确告诉我为什么，不要打印一个空结果就说完成了。API Key 从环境变量 ARK_AGENT_PLAN_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_C='写一个 main.py，用火山方舟 Agent Plan 给下面三段文本做向量化，**向量维度要 1024**，最后把每条向量的实际长度打印出来确认。三段文本：["今天天气很好", "这部电影非常精彩", "服务器响应超时了"]。API Key 从环境变量 ARK_AGENT_PLAN_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

run_one () {
  local scen="$1" cfg="$2" run="$3" task="$4"
  local out="$ROOT/$scen/$cfg/run-$run"
  local target="$out/outputs/main.py"
  [[ -f "$target" ]] && { echo "skip  $scen/$cfg/run-$run"; return; }
  mkdir -p "$out/outputs"

  local preamble
  if [[ "$cfg" == "with_skill" ]]; then
    preamble="有一份接入说明书可以用，请先读 $SKILL 并按它的指引去读它指向的 references 文件，再动手。"
  else
    preamble="不要读取 $SKILLDIR 目录下的任何文件（也不要读任何 .skill 文件）。"
  fi

  local prompt="你在替用户完成一个编程任务。$preamble
你可以用 WebFetch 抓取官方文档来确认接口细节，建议这么做。
不要真的调用 API（当前环境没有可用的 Key），写好代码即可，可以用 python3 -m py_compile 验证能编译。

用户任务（用中文回答）：
$task

交付：把脚本原样保存到 $target 这个路径，别的文件不用存。"

  local t0=$(date +%s)
  ( cd "$out" && env -u CLAUDECODE -u CLAUDE_CODE_SSE_PORT \
      ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic" \
      ANTHROPIC_AUTH_TOKEN="$GLM_CODING_PLAN_API_KEY" \
      ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.3 \
      ANTHROPIC_DEFAULT_OPUS_MODEL=glm-5.3 \
      ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-5.3-flash \
      API_TIMEOUT_MS=900000 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
      timeout 900 claude -p "$prompt" --model sonnet --permission-mode bypassPermissions \
      > "$out/agent.log" 2>&1 )
  local rc=$? t1=$(date +%s)
  echo "{\"exit\": $rc, \"seconds\": $((t1-t0)), \"executor\": \"glm-5.3\"}" > "$out/agent_meta.json"
  if [[ -f "$target" ]]; then echo "OK    $scen/$cfg/run-$run  ($((t1-t0))s)"; else echo "FAIL  $scen/$cfg/run-$run  rc=$rc ($((t1-t0))s)"; fi
}

pids=()
for run in 1 2 3 4 5; do
  for cfg in with_skill without_skill; do
    run_one anthropic-entry-model-pinning "$cfg" "$run" "$TASK_A" & pids+=($!)
    run_one kimi-max-tokens-empty         "$cfg" "$run" "$TASK_B" & pids+=($!)
    run_one plan-embeddings-shape         "$cfg" "$run" "$TASK_C" & pids+=($!)
  done
  for p in $pids; do wait $p; done
  pids=()
  echo "--- run-$run 批次完成 ---"
done
echo "全部完成：$(find "$ROOT" -name main.py | wc -l)/30"
