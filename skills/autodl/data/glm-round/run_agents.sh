#!/bin/zsh
# 用 GLM-5.3 作为执行 Agent 跑 autodl 的 30 次任务（Claude Code CLI 仅作 harness）
# 用法： GLM_CODING_PLAN_API_KEY=... ./run_agents.sh
set -u
ROOT="${0:A:h}"
: "${GLM_CODING_PLAN_API_KEY:?export GLM_CODING_PLAN_API_KEY first}"

SKILL=/Users/chopinfeng/Workspace/Skillify/autodl/SKILL.md
SKILLDIR=/Users/chopinfeng/Workspace/Skillify/autodl

TASK_A='写一个 main.py，给运维值班用：查一下我们 AutoDL 账号的余额，**可用余额低于 20 元就报警**（打印醒目告警），并把可用余额按「元」打印出来。这个脚本会挂到监控上，所以数字必须准——上次有个同事把单位搞错，告警一直没响，等发现的时候实例已经因为欠费被停了。Token 从环境变量 AUTODL_TOKEN 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_B='写一个 main.py，查一台 AutoDL 实例的当前状态，实例 UUID 从环境变量 AUTODL_INSTANCE_UUID 读取。有个要求：**要能区分「这台实例不存在」和「我的请求本身写错了」这两种情况**，分别给出不同的提示——排查的时候这两种原因的处理方式完全不同，混在一起会让人白折腾。Token 从环境变量 AUTODL_TOKEN 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_C='写一个 main.py 帮我们探路：我们准备用 AutoDL 的弹性部署跑一个推理服务，先确认**我们账号现在到底能不能创建部署**，顺便查一下 RTX 4090 有没有库存。如果不能创建部署，请明确告诉我到底是什么原因——是账号资质问题、还是接口用错了、还是服务本身有问题，这三种我们的应对完全不一样。注意：这一步只是探路，**不要真的创建任何部署或实例**。Token 从环境变量 AUTODL_TOKEN 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

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
不要真的调用 API（当前环境没有可用的 Token），写好代码即可，可以用 python3 -m py_compile 验证能编译。

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
    run_one balance-unit                "$cfg" "$run" "$TASK_A" & pids+=($!)
    run_one get-params-style            "$cfg" "$run" "$TASK_B" & pids+=($!)
    run_one deployment-permission-probe "$cfg" "$run" "$TASK_C" & pids+=($!)
  done
  for p in $pids; do wait $p; done
  pids=()
  echo "--- run-$run 批次完成 ---"
done
echo "全部完成：$(find "$ROOT" -name main.py | wc -l)/30"
