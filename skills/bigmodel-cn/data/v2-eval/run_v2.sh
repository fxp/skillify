#!/bin/zsh
# v2（精简后的说明书）A/B 评测：8 个场景 × n=5 = 40 次运行，只跑 with_skill。
# 对照组直接复用既有的 v1 with_skill 与 baseline 记录——任务文本逐字相同，harness 完全一致。
# 用法： GLM_CODING_PLAN_API_KEY=... ./run_v2.sh
set -u
ROOT="${0:A:h}"
: "${GLM_CODING_PLAN_API_KEY:?export GLM_CODING_PLAN_API_KEY first}"
SKILL=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-v2/SKILL.md

run_one () {
  local scen="$1" run="$2" task="$3"
  local out="$ROOT/$scen/with_skill/run-$run"
  local target="$out/outputs/main.py"
  [[ -f "$target" ]] && { echo "skip  $scen/run-$run"; return; }
  mkdir -p "$out/outputs"

  local prompt="你在替用户完成一个编程任务。有一份接入说明书可以用，请先读 $SKILL 并按它的指引去读它指向的 references 文件，再动手。
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
  echo "{\"exit\": $rc, \"seconds\": $((t1-t0)), \"executor\": \"glm-5.3\", \"skill\": \"v2\"}" > "$out/agent_meta.json"
  [[ -f "$target" ]] && echo "OK    $scen/run-$run  ($((t1-t0))s)" || echo "FAIL  $scen/run-$run  rc=$rc"
}

# 任务文本从 tasks.json 读，逐字沿用原轮次，保证 A/B 只变说明书这一个变量
eval "$(python3 - "$ROOT/tasks.json" <<'PY'
import json, shlex, sys
t = json.load(open(sys.argv[1], encoding="utf-8"))
print("SCENS=(" + " ".join(shlex.quote(k) for k in t) + ")")
for k, (rd, task) in t.items():
    print(f"TASK_{k.replace('-','_')}={shlex.quote(task)}")
PY
)"

pids=()
for run in 1 2 3 4 5; do
  for scen in $SCENS; do
    var="TASK_${scen//-/_}"
    run_one "$scen" "$run" "${(P)var}" & pids+=($!)
  done
  for p in $pids; do wait $p; done
  pids=()
  echo "--- run-$run 批次完成 ---"
done
echo "全部完成：$(find "$ROOT" -path '*/outputs/main.py' | wc -l)/40"
