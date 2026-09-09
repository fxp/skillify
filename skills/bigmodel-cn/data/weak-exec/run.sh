#!/bin/zsh
# 弱执行器轮：执行 Agent 换成 glm-4.5-flash，让天花板降下来，
# 才测得出 v1→v2 这次优化对准确率的边际价值。
# 用法： SKILL_VER=v1|v2 GLM_CODING_PLAN_API_KEY=... ./run.sh
set -u
ROOT="${0:A:h}"
: "${GLM_CODING_PLAN_API_KEY:?export GLM_CODING_PLAN_API_KEY first}"
VER="${SKILL_VER:?export SKILL_VER=v1 或 v2}"
case "$VER" in
  v1) SKILL=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-v1-archive/SKILL.md ;;
  v2) SKILL=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn/SKILL.md ;;
  v4) SKILL=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-v4/SKILL.md ;;
  *)  echo "未知版本 $VER"; exit 1 ;;
esac
[[ -f "$SKILL" ]] || { echo "找不到 $SKILL"; exit 1; }
EXEC_MODEL=glm-4.5-flash

run_one () {
  local scen="$1" run="$2" task="$3"
  local out="$ROOT/$VER/$scen/run-$run"
  local target="$out/outputs/main.py"
  [[ -f "$target" ]] && { echo "skip  $VER/$scen/run-$run"; return; }
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
      ANTHROPIC_DEFAULT_SONNET_MODEL=$EXEC_MODEL \
      ANTHROPIC_DEFAULT_OPUS_MODEL=$EXEC_MODEL \
      ANTHROPIC_DEFAULT_HAIKU_MODEL=$EXEC_MODEL \
      API_TIMEOUT_MS=900000 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
      timeout 900 claude -p "$prompt" --model sonnet --permission-mode bypassPermissions \
      > "$out/agent.log" 2>&1 )
  local rc=$? t1=$(date +%s)
  echo "{\"exit\": $rc, \"seconds\": $((t1-t0)), \"executor\": \"$EXEC_MODEL\", \"skill\": \"$VER\"}" > "$out/agent_meta.json"
  [[ -f "$target" ]] && echo "OK    $VER/$scen/run-$run ($((t1-t0))s)" || echo "FAIL  $VER/$scen/run-$run rc=$rc"
}

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
  echo "--- $VER run-$run 完成 ---"
done
echo "$VER: $(find "$ROOT/$VER" -path '*/outputs/main.py' | wc -l)/40"
