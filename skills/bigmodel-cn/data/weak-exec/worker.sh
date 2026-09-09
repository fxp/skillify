#!/bin/zsh
# 单次运行的 worker，由 xargs -P 调度。参数： ver|scen|run
set -u
ROOT="${0:A:h}"
EXEC_MODEL=glm-4.5-flash
item="$1"
ver="${item%%|*}"; rest="${item#*|}"; scen="${rest%%|*}"; run="${rest##*|}"
[[ "$ver" == "v1" ]] && skill=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-v1-archive/SKILL.md \
                     || skill=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn/SKILL.md
out="$ROOT/$ver/$scen/run-$run"
target="$out/outputs/main.py"
[[ -f "$target" ]] && { echo "skip $ver/$scen/run-$run"; exit 0; }
task=$(python3 -c "
import json,sys
t=json.load(open('$ROOT/tasks.json',encoding='utf-8'))
sys.stdout.write(t['$scen'][1])")
mkdir -p "$out/outputs"
prompt="你在替用户完成一个编程任务。有一份接入说明书可以用，请先读 $skill 并按它的指引去读它指向的 references 文件，再动手。
你可以用 WebFetch 抓取官方文档来确认接口细节，建议这么做。
不要真的调用 API（当前环境没有可用的 Key），写好代码即可，可以用 python3 -m py_compile 验证能编译。

用户任务（用中文回答）：
$task

交付：把脚本原样保存到 $target 这个路径，别的文件不用存。"
t0=$(date +%s)
( cd "$out" && env -u CLAUDECODE -u CLAUDE_CODE_SSE_PORT \
    ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic" \
    ANTHROPIC_AUTH_TOKEN="$GLM_CODING_PLAN_API_KEY" \
    ANTHROPIC_DEFAULT_SONNET_MODEL=$EXEC_MODEL \
    ANTHROPIC_DEFAULT_OPUS_MODEL=$EXEC_MODEL \
    ANTHROPIC_DEFAULT_HAIKU_MODEL=$EXEC_MODEL \
    API_TIMEOUT_MS=900000 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    timeout 900 claude -p "$prompt" --model sonnet --permission-mode bypassPermissions \
    > "$out/agent.log" 2>&1 )
rc=$?; t1=$(date +%s)
echo "{\"exit\": $rc, \"seconds\": $((t1-t0)), \"executor\": \"$EXEC_MODEL\", \"skill\": \"$ver\"}" > "$out/agent_meta.json"
[[ -f "$target" ]] && echo "OK   $ver/$scen/run-$run ($((t1-t0))s)" || echo "FAIL $ver/$scen/run-$run rc=$rc"
