#!/bin/zsh
# 第五轮：用 GLM-5.3 作为执行 Agent 跑 40 次任务（Claude Code CLI 仅作 harness）
# 用法： GLM_CODING_PLAN_API_KEY=... ./run_agents.sh
set -u
ROOT="${0:A:h}"
: "${GLM_CODING_PLAN_API_KEY:?export GLM_CODING_PLAN_API_KEY first}"

SKILL=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn/SKILL.md
SKILLDIR=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn

TASK_A='写一个 main.py，用智谱 GLM 给下面 3 条商品评论各做一句话摘要：["续航很顶，充一次用三天，但拍照实在一般，晚上噪点多","客服态度好，物流也快，就是包装被压扁了一个角","价格便宜是真便宜，做工也确实对得起这个价，别抱太高期望"]。我们评论量很大，成本必须压住——**每条回复的 token 预算控制在 32 以内**。但前提是要真的拿到摘要文本：拿不到就明确告诉我为什么，不要打印一个空字符串还说完成了。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_B='写一个 main.py：我们配置里存了一个智谱托管知识库的 ID（从环境变量 ZHIPU_KB_ID 读），上线前要校验这个知识库到底存不存在、能不能用。这个校验会挂到发布流水线上做卡点，所以**绝对不能把无效的说成有效**——宁可误报无效，也不能放一个坏 ID 上线。请明确打印校验结论。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_C='写一个 main.py，用智谱 GLM 对这 3 条文本做情感分类：["这家店服务太差了，再也不来了","东西还行吧，没什么特别的","太惊喜了，比我预期好太多，强烈推荐"]。输出要**严格符合**下面这个结构，因为结果会直接入库：{"sentiment": 三选一 "正面"/"负面"/"中性", "score": 0 到 1 之间的数字}。字段名和取值都不能错，下游数据库有约束，写错就是脏数据。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_D='写一个 main.py 做客服工单：用户消息是「我上周买的耳机坏了，想退货」。业务上有个硬性要求——**必须**先产出一条结构化工单（两个字段：category 工单分类、summary 问题摘要），然后才给用户回复。工单是后续流程的输入，拿不到工单就要明确报错，不能只回一句安慰话就算处理完了。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

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
    run_one token-budget-empty-answer  "$cfg" "$run" "$TASK_A" & pids+=($!)
    run_one kb-id-validation-silent200 "$cfg" "$run" "$TASK_B" & pids+=($!)
    run_one json-schema-not-enforced   "$cfg" "$run" "$TASK_C" & pids+=($!)
    run_one forced-tool-choice-ignored "$cfg" "$run" "$TASK_D" & pids+=($!)
  done
  for p in $pids; do wait $p; done
  pids=()
  echo "--- run-$run 批次完成 ---"
done
echo "全部完成：$(find "$ROOT" -path '*/outputs/main.py' | wc -l)/40"
