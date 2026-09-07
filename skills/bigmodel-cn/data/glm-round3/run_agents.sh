#!/bin/zsh
# 用 GLM-5.3 作为执行 Agent 跑全部 12 次任务（Claude Code CLI 仅作 harness）
# 用法： GLM_CODING_PLAN_API_KEY=... ./run_agents.sh
set -u
ROOT="${0:A:h}"
: "${GLM_CODING_PLAN_API_KEY:?export GLM_CODING_PLAN_API_KEY first}"

SKILL=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn/SKILL.md

TASK_A='写一个 main.py，做一个联网问答小工具：脚本里写死一个问题「2026 年智谱 BigModel 发布了哪些新模型」，调用智谱的模型带联网搜索来回答，把答案打印到 stdout。重要要求：答案下面必须列出这次回答实际参考的信息来源，每条包含来源标题和可点击的 URL——这些来源必须是接口真实返回给你的，不能让模型自己凭印象编链接，我要能点进去核对。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_B='同目录下有一份 faq.txt，每行一条常见问题（一共一百多条）。写一个 main.py 建一个最小可用的检索：用智谱的 embedding-3 把每一行都向量化，结果存成同目录的 vectors.json，然后用「发票怎么开」这句话做查询，算余弦相似度取 top-3，把这三条最相近的原文打印到 stdout。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests（numpy 也不要用，自己算），脚本要能直接 python3 main.py 跑通。'

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
    run_one cited-web-answer "$cfg" "$run" "$TASK_A" &
    pids+=($!)
    run_one rag-index-embeddings "$cfg" "$run" "$TASK_B" &
    pids+=($!)
  done
  for p in $pids; do wait $p; done
  pids=()
  echo "--- run-$run 批次完成 ---"
done
echo "全部完成：$(find "$ROOT" -name main.py | wc -l)/12"
