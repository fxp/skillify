#!/bin/zsh
# 用 GLM-5.3 作为执行 Agent 跑全部 12 次任务（Claude Code CLI 仅作 harness）
# 用法： GLM_CODING_PLAN_API_KEY=... ./run_agents.sh
set -u
ROOT="${0:A:h}"
: "${GLM_CODING_PLAN_API_KEY:?export GLM_CODING_PLAN_API_KEY first}"

SKILL=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn/SKILL.md

TASK_A='我买了智谱的 GLM Coding Plan Max 套餐，额度肯定没用完。下面这段代码一直报 429，{"error": {"code": "1113", "message": "余额不足或无可用资源包,请充值。"}}。帮我改成一份能跑通的 main.py：读环境变量 GLM_KEY 拿 Key，问模型"用一句话介绍 Python"，把回答打印到 stdout。只能用 requests。原代码：import os, requests; r = requests.post("https://open.bigmodel.cn/api/paas/v4/chat/completions", headers={"Authorization": f"Bearer {os.environ[chr(39)+chr(39)]}"}, json={"model": "glm-5.3", "messages": [{"role":"user","content":"用一句话介绍 Python"}]}); print(r.json())'

TASK_B='写一个 main.py，把同目录下的 faq.txt（一百多行常见问题）灌进智谱的托管知识库：建库、上传文档。关键要求：**在脚本告诉我"成功"之前，必须先确认这些文档确实已经可以被检索到**——我被这个坑过，上次上传显示成功、结果检索永远是空的，白白排查了半天。所以请务必加一个校验环节，确认不可用就明确报错告诉我原因，不要报喜不报忧。最后无论成功失败都把知识库清理掉。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_C='写一个 main.py，用智谱的**异步**对话接口（async/chat/completions + 轮询结果）跑一个批量任务：对三句话做情感分类。我们有审计要求，必须锁定模型版本用 glm-4.6，所以脚本跑完要把「我请求的模型」和「接口实际使用的模型」都打印出来做核对，两者不一致必须明确报警——审计上这个不能含糊。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

run_one () {
  local scen="$1" cfg="$2" run="$3" task="$4"
  local out="$ROOT/$scen/$cfg/run-$run"
  local target="$out/outputs/main.py"
  [[ -f "$target" ]] && { echo "skip  $scen/$cfg/run-$run"; return; }

  local preamble
  if [[ "$cfg" == "with_skill" ]]; then
    preamble="有一份接入说明书可以用，请先读 $SKILL 并按它的指引去读它指向的 references 文件，再动手。"
  else
    preamble="不要读取 /Users/chopinfeng/Workspace/Skillify/bigmodel-cn 目录下的任何文件（也不要读任何 .skill 文件）。"
  fi

  local prompt="你在替用户完成一个编程任务。$preamble
你可以用 WebFetch 抓取官方文档来确认接口细节，建议这么做。
不要真的调用大模型 API（当前环境没有可用的 Key），写好代码即可，可以用 python3 -m py_compile 验证能编译。

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
    run_one plan-1113-fix "$cfg" "$run" "$TASK_A" &
    pids+=($!)
    run_one kb-upload-readiness "$cfg" "$run" "$TASK_B" &
    pids+=($!)
    run_one async-model-pinning "$cfg" "$run" "$TASK_C" &
    pids+=($!)
  done
  for p in $pids; do wait $p; done
  pids=()
  echo "--- run-$run 批次完成 ---"
done
echo "全部完成：$(find "$ROOT" -name main.py | wc -l)/12"
