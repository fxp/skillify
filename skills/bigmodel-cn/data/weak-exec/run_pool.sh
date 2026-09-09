#!/bin/zsh
# 并发池版：没有批次栅栏，v1/v2 一起排队，并发上限 POOL。
# 已有 outputs/main.py 的会跳过，不重复跑。
set -u
ROOT="${0:A:h}"
: "${GLM_CODING_PLAN_API_KEY:?export GLM_CODING_PLAN_API_KEY first}"
POOL="${POOL:-10}"
EXEC_MODEL=glm-4.5-flash
V1=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-v1-archive/SKILL.md
V2=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn/SKILL.md

eval "$(python3 - "$ROOT/tasks.json" <<'PY'
import json, shlex, sys
t = json.load(open(sys.argv[1], encoding="utf-8"))
print("SCENS=(" + " ".join(shlex.quote(k) for k in t) + ")")
for k, (rd, task) in t.items():
    print(f"TASK_{k.replace('-','_')}={shlex.quote(task)}")
PY
)"

run_one () {
  local ver="$1" scen="$2" run="$3" task="$4" skill="$5"
  local out="$ROOT/$ver/$scen/run-$run"
  local target="$out/outputs/main.py"
  [[ -f "$target" ]] && return
  mkdir -p "$out/outputs"
  local prompt="你在替用户完成一个编程任务。有一份接入说明书可以用，请先读 $skill 并按它的指引去读它指向的 references 文件，再动手。
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
  echo "{\"exit\": $rc, \"seconds\": $((t1-t0)), \"executor\": \"$EXEC_MODEL\", \"skill\": \"$ver\"}" > "$out/agent_meta.json"
  [[ -f "$target" ]] && echo "OK   $ver/$scen/run-$run (${$((t1-t0))}s)" || echo "FAIL $ver/$scen/run-$run rc=$rc"
}

# 组装任务队列：先补 v1 缺的，再跑 v2
typeset -a QUEUE
for ver in v1 v2; do
  for run in 1 2 3 4 5; do
    for scen in $SCENS; do
      [[ -f "$ROOT/$ver/$scen/run-$run/outputs/main.py" ]] && continue
      QUEUE+=("$ver|$scen|$run")
    done
  done
done
echo "待跑 ${#QUEUE[@]} 次，并发 $POOL"

running=0
for item in $QUEUE; do
  ver="${item%%|*}"; rest="${item#*|}"; scen="${rest%%|*}"; run="${rest##*|}"
  var="TASK_${scen//-/_}"
  [[ "$ver" == "v1" ]] && sk="$V1" || sk="$V2"
  # zsh 没有 bash 的 wait -n，之前的 `|| wait` 回退等于每 POOL 个就全等一次，
  # 栅栏又回来了。改成轮询运行中的作业数，保持真并发。
  while (( $(jobs -r 2>/dev/null | wc -l) >= POOL )); do sleep 3; done
  run_one "$ver" "$scen" "$run" "${(P)var}" "$sk" &
done
wait
echo "完成 v1=$(find "$ROOT/v1" -path '*/outputs/main.py'|wc -l)/40  v2=$(find "$ROOT/v2" -path '*/outputs/main.py'|wc -l)/40"
