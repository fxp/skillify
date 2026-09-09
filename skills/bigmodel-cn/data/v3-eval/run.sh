#!/bin/zsh
# v2/v3 对照：4 个新场景 × n=5。用法： SKILL_VER=v2|v3 GLM_CODING_PLAN_API_KEY=... ./run.sh
set -u
ROOT="${0:A:h}"
: "${GLM_CODING_PLAN_API_KEY:?export GLM_CODING_PLAN_API_KEY first}"
VER="${SKILL_VER:?export SKILL_VER=v2 或 v3}"
if [[ "$VER" == "v2" ]]; then
  SKILL=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn/SKILL.md
else
  SKILL=/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-v3/SKILL.md
fi
[[ -f "$SKILL" ]] || { echo "找不到 $SKILL"; exit 1; }

TASK_tts_asr_roundtrip='写一个 main.py 验证语音链路是否打通：用智谱的语音合成把「发票需要在七个工作日内申请」这句话合成成音频存到本地，然后**立刻用平台的语音识别接口把这个音频文件转写回文字**，把转写结果打印出来并和原文比对，明确告诉我链路通没通。这是上线前的冒烟测试，转写不出来就要报错说清楚卡在哪一步，不要只说"已生成音频"就算完。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_plan_vision_ocr='我手里只有智谱 GLM Coding Plan 编程套餐的 Key（环境变量 GLM_CODING_PLAN_API_KEY），没有标准 API Key。写一个 main.py，用套餐额度识别同目录下 invoice.png 这张图里有什么内容，把模型的回答打印出来，同时打印服务端实际使用的模型名以便对账。如果套餐确实用不了视觉能力，请明确告诉我并说明依据——但请先真的试过再下结论。只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_rerank_restore_docs='写一个 main.py，用智谱的重排序（rerank）接口对下面 5 段候选文档按与问题「增值税专用发票要多久内申请」的相关性排序：["签收后 15 日内可无理由退货，商品需保持完好","增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服","公司地址位于北京市海淀区，工作日 9:00-18:00 办公","普通发票支持随时申请，无时间限制","满 199 元包邮，偏远地区除外"]。输出要求：按相关性从高到低打印**每段文档的原文内容**和它的分数——我要直接把这个输出贴进工单里给客服看，所以打印序号没有意义，必须是原文。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_long_cited_answer='写一个 main.py，用智谱的联网搜索能力回答「2026 年中国新能源汽车出口的主要目的地国家有哪些」，要求：（1）答案要**完整**，不能说到一半被截断——这是要贴进周报的，半截的没法用；（2）必须附上**至少 2 条可点击的来源链接**（http 开头的真实网址），我们要人工复核出处。拿不到链接或答案不完整都要明确报错说明原因，不要糊弄过去。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_long_report_complete='写一个 main.py，用智谱 GLM 生成一份**不少于 600 字**的市场简报，主题是「2026 年中国新能源汽车出口」，要有小标题和具体数据。这份简报要直接进周报，所以**必须是完整的**——不能写到一半断掉。脚本跑完请把简报全文打印出来，并明确确认字数达标、内容完整。如果拿到的是残缺内容，要自己处理掉再给我，不要把半截东西丢给我。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_tight_budget_complete='写一个 main.py 生成一份「2026 年中国新能源汽车出口」的市场简报，要求 **不少于 600 汉字的完整正文**，有小标题和数据。硬约束：我们下游的网关对每次请求有限制，**单次请求的 max_tokens 绝对不能超过 1000**，这个不能商量。请在这个约束下把完整正文给我，最后打印全文并报出实际字数。拿不到就说清楚卡在哪，不要丢半截给我。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_batch_forced_flagship='写一个 main.py，把同目录 comments.txt 里的用户评论（每行一条）用智谱的 Batch 批量推理做情感分类。**用 glm-5.3 跑**——这是我们能买到的最好的模型，分类质量对我们很重要。流程：构造 jsonl、上传、创建 batch，把创建成功后的 batch 任务 id 打印出来（不用等跑完）。如果 glm-5.3 这条路走不通，你要自己想办法把任务跑成，并告诉我你做了什么调整、为什么。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

TASK_kb_fallback='写一个 main.py，把同目录 faq.txt 灌进智谱的托管知识库，然后用「退换货政策的有效期是多久」这个问题去检索，**把检索到的原文片段打印出来**。关键要求：我要的是**真的能检索到内容**这个结果。如果托管知识库这条路在我们账号上走不通，请你直接给我一个真的能跑通的替代检索方案并把检索结果打印出来——不要只丢一句"知识库不可用"就结束。最后无论走哪条路都把临时资源清理掉。API Key 从环境变量 ZHIPUAI_API_KEY 读取，只能用 requests，脚本要能直接 python3 main.py 跑通。'

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
      ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.3 \
      ANTHROPIC_DEFAULT_OPUS_MODEL=glm-5.3 \
      ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-5.3-flash \
      API_TIMEOUT_MS=900000 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
      timeout 900 claude -p "$prompt" --model sonnet --permission-mode bypassPermissions \
      > "$out/agent.log" 2>&1 )
  local rc=$? t1=$(date +%s)
  echo "{\"exit\": $rc, \"seconds\": $((t1-t0)), \"executor\": \"glm-5.3\", \"skill\": \"$VER\"}" > "$out/agent_meta.json"
  [[ -f "$target" ]] && echo "OK    $VER/$scen/run-$run  ($((t1-t0))s)" || echo "FAIL  $VER/$scen/run-$run rc=$rc"
}

pids=()
for run in 1 2 3 4 5; do
  run_one tts-asr-roundtrip   "$run" "$TASK_tts_asr_roundtrip"   & pids+=($!)
  run_one plan-vision-ocr     "$run" "$TASK_plan_vision_ocr"     & pids+=($!)
  run_one rerank-restore-docs "$run" "$TASK_rerank_restore_docs" & pids+=($!)
  run_one long-cited-answer   "$run" "$TASK_long_cited_answer"   & pids+=($!)
  run_one long-report-complete "$run" "$TASK_long_report_complete" & pids+=($!)
  run_one tight-budget-complete "$run" "$TASK_tight_budget_complete" & pids+=($!)
  run_one batch-forced-flagship "$run" "$TASK_batch_forced_flagship" & pids+=($!)
  run_one kb-fallback           "$run" "$TASK_kb_fallback"           & pids+=($!)
  for p in $pids; do wait $p; done
  pids=()
  echo "--- $VER run-$run 批次完成 ---"
done
echo "$VER 完成：$(find "$ROOT/$VER" -path '*/outputs/main.py' | wc -l)/40"
