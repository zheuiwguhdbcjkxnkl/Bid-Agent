/* 视图：文件与解析 / 要求与评分 / 响应规划
   对应文档 5.6–5.8。 */

/* ---------------- 文件与解析 /projects/{id}/documents（文档 5.6） ---------------- */
window.Views.documents = (container, id) => {
  container.innerHTML = UI.topbar("文件与解析", "文件与解析",
    `<button class="btn btn-primary btn-sm" id="up-new">${Icons.upload({ size: 14 })} 上传新文件</button>`) +
    `<div id="doc-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + `/projects/${id}/documents`).then((docs) => {
    let activeObj = docs.objects[0];

    const render = () => {
      const versions = docs.versions.filter((v) => v.objectId === activeObj.id);
      const segs = docs.segments;
      const isImpact = ["澄清文件", "更正文件", "补遗文件"].includes(activeObj.type);

      const left = docs.objects.map((o) => {
        const cls = o.id === activeObj.id ? "active" : "";
        return `<div class="col-item ${cls}" data-id="${o.id}">
          <div class="ci-title">${UI.esc(o.name)} ${o.stale ? `<span class="badge stale">待复核</span>` : ""}</div>
          <div class="ci-meta">${UI.esc(o.type)} · ${UI.esc(o.source)}</div>
          <div class="ci-row"><span>版本 ${UI.esc(o.version)}</span><span>${statusBadge(o.status)}</span></div>
        </div>`;
      }).join("");

      const mid = `
        <h3>版本时间线</h3>
        <ul class="timeline">
          ${versions.map((v) => `<li class="${v.state === "STALE" ? "warn" : ""}">
            <div class="tl-time num">${UI.fmtDateTime(v.time)}</div>
            <div class="tl-title">${UI.esc(v.label)} ${v.state === "STALE" ? `<span class="badge stale">已失效</span>` : statusBadge(v.state)}</div>
            <div class="tl-desc">${UI.esc(v.relation)}</div>
          </li>`).join("")}
        </ul>
        <h3 style="margin-top:12px">解析状态与任务进度</h3>
        <div class="card" style="padding:12px 14px">
          ${statusBadge(activeObj.status)}
          <div class="row" style="margin-top:10px;gap:8px">
            <button class="btn btn-sm" id="btn-parse">${Icons.refresh({ size: 13 })} 解析</button>
            <button class="btn btn-sm" id="btn-reparse">${Icons.retry({ size: 13 })} 重新解析</button>
          </div>
          ${activeObj.status === "PARSE_FAILED" ? `<div class="notice error" style="margin-top:10px">${Icons.alert({ size: 14 })}<span class="nt-body"><span class="nt-title">解析失败（前端不得显示为成功）</span><span class="nt-desc">位置：${UI.esc(docs.failed.location)}；原因：${UI.esc(docs.failed.reason)}</span></span><div style="margin-top:8px"><button class="btn btn-sm" onclick="UI.toast('已触发重试','info')">${Icons.retry({ size: 13 })} 重试</button> <button class="btn btn-sm" onclick="UI.toast('转人工处理','info')">${Icons.user({ size: 13 })} 人工处理</button></div></div>` : ""}
        </div>
        ${isImpact ? `<div class="notice warning" style="margin-top:12px">${Icons.alert({ size: 14 })}<span class="nt-body"><span class="nt-title">${UI.esc(activeObj.type)}：影响范围已突出</span><span class="nt-desc">该文件会使依赖旧版本的要求、审核与基线标记为 STALE / 待复核，需重新确认相关关口。</span></span></div>` : ""}
      `;

      const right = `
        <h3>原文预览与结构化结果</h3>
        <div class="table-wrap"><table class="grid">
          <thead><tr><th>页码</th><th>章节路径</th><th>原文摘要</th><th>结构化</th><th>来源</th></tr></thead>
          <tbody>${segs.map((s) => `<tr>
            <td class="num">p${s.page}</td>
            <td class="text-xs">${UI.esc(s.path)}</td>
            <td>${UI.esc(s.text)}</td>
            <td>${UI.esc(s.structured.type)} ${riskBadge(s.structured.risk)}</td>
            <td class="text-xs">${UI.esc(s.source)}</td>
          </tr>`).join("")}</tbody>
        </table></div>
        <div class="row" style="margin-top:10px;gap:8px">
          <button class="btn btn-sm" id="btn-seg">${Icons.eye({ size: 13 })} 查看片段</button>
          <button class="btn btn-sm" id="btn-correction">${Icons.authoring({ size: 13 })} 提交人工修正</button>
        </div>
      `;

      document.getElementById("doc-content").innerHTML = `
        <div class="card">
          <div class="notice info">${Icons.info({ size: 14 })}<span class="nt-body"><span class="nt-title">三栏布局</span><span class="nt-desc">左侧文件对象与状态；中间版本时间线与解析；右侧原文预览与结构化结果。关键结论可跳转来源文件与页码。</span></span></div>
          <div class="three-col" style="margin-top:14px">
            <div class="col-panel"><h3>文件逻辑对象</h3>${left}
              <button class="btn btn-sm btn-block" id="up-ver" style="margin-top:8px">${Icons.upload({ size: 13 })} 上传新版本</button>
            </div>
            <div class="col-panel">${mid}</div>
            <div class="col-panel">${right}</div>
          </div>
        </div>`;

      document.querySelectorAll(".col-item").forEach((el) => el.onclick = () => { activeObj = docs.objects.find((o) => o.id === el.dataset.id); render(); });
      document.getElementById("btn-parse").onclick = () => UI.toast("已创建解析任务（轮询中）", "info");
      document.getElementById("btn-reparse").onclick = () => UI.toast("已创建重新解析任务", "info");
      document.getElementById("btn-seg").onclick = () => {
        UI.drawer({ title: "原文片段预览", body: segs.map((s) => `<div class="card" style="padding:12px 14px"><div class="text-xs muted">p${s.page} · ${UI.esc(s.path)} · ${UI.esc(s.source)}</div><div style="margin-top:4px">${UI.esc(s.text)}</div></div>`).join(""), footer: `<button class="btn" onclick="UI.closeDrawer()">关闭</button>` });
      };
      document.getElementById("btn-correction").onclick = () => {
        UI.modal({ title: "提交人工修正", body: `<div class="field"><label>修正说明</label><textarea class="control" placeholder="对解析结果的人工修正说明"></textarea></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已提交人工修正','success')">提交</button>` });
      };
      document.getElementById("up-ver").onclick = () => UI.toast("上传新版本：新版本将使依赖旧版本的结果标记为 STALE", "info");
    };
    render();

    document.getElementById("up-new").onclick = () => {
      UI.modal({ title: "上传新文件", body: `<div class="field"><label>文件</label><input type="file" class="control" /></div><div class="field"><label>来源</label><input class="control" placeholder="例如：政府采购网" /></div><div class="field"><label>文件分类</label><select class="control"><option>采购文件</option><option>技术附件</option><option>澄清文件</option><option>补遗文件</option></select></div><div class="field"><label>是否作为初始有效版本</label><select class="control"><option>是</option><option>否</option></select></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已上传并触发解析','success')">上传</button>` });
    };
  }).catch((err) => UI.handleError(err));
};

/* ---------------- 要求与评分 /projects/{id}/requirements（文档 5.7） ---------------- */
window.Views.requirements = (container, id) => {
  container.innerHTML = UI.topbar("要求与评分", "要求与评分",
    `<button class="btn btn-primary btn-sm" id="confirm-baseline" disabled title="存在未处理阻断项或高风险未确认时不可用">${Icons.gate({ size: 14 })} 要求基线确认</button>`) +
    `<div id="req-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + `/projects/${id}/requirements`).then((data) => {
    const types = ["资格条件", "否决项", "实质性要求", "技术商务要求", "评分项", "时间节点"];
    let activeType = "全部";
    let selected = [];
    const b = data.baseline;

    const canConfirm = b.blockers.length === 0 && b.highUnconfirmed.length === 0;

    const render = () => {
      const list = data.items.filter((r) => activeType === "全部" || r.type === activeType);
      const rows = list.map((r) => `<tr data-id="${r.id}">
        <td><input type="checkbox" class="row-check" value="${r.id}" ${selected.includes(r.id) ? "checked" : ""} ${r.risk === "HIGH" || r.risk === "BLOCK" ? "disabled title='高风险/阻断须逐项确认'" : ""}></td>
        <td class="num">${UI.esc(r.no)}</td>
        <td>${UI.esc(r.type)}</td>
        <td class="td-clamp">${UI.esc(r.summary)}</td>
        <td class="num">p${r.page}</td>
        <td>${UI.esc(r.package)}</td>
        <td>${riskBadge(r.risk)}</td>
        <td>${r.status === "已确认" ? `<span class="badge success"><span class="dot solid"></span>已确认</span>` : `<span class="badge warning"><span class="dot solid"></span>待确认</span>`}</td>
        <td>${UI.esc(r.owner)}</td>
        <td>${UI.esc(r.section)}</td>
        <td>${r.evidence === "证据不足" || r.evidence === "证据待补充" ? `<span class="badge danger-high">${UI.esc(r.evidence)}</span>` : UI.esc(r.evidence)}</td>
        <td>
          <button class="btn btn-sm" data-act="view" data-id="${r.id}">${Icons.eye({ size: 13 })}</button>
          <button class="btn btn-sm" data-act="edit" data-id="${r.id}">${Icons.authoring({ size: 13 })}</button>
          <button class="btn btn-sm" data-act="split" data-id="${r.id}" title="拆分混合要求">${Icons.split({ size: 13 })}</button>
          <button class="btn btn-sm" data-act="merge" data-id="${r.id}" title="合并重复要求">${Icons.merge({ size: 13 })}</button>
          <button class="btn btn-sm" data-act="pending" data-id="${r.id}">标记待确认</button>
          <button class="btn btn-sm" data-act="owner" data-id="${r.id}">分配责任人</button>
          <button class="btn btn-sm" data-act="conflict" data-id="${r.id}">查看冲突</button>
        </td>
      </tr>`).join("");

      const tabs = ["全部", ...types].map((t) => `<span class="tab ${activeType === t ? "active" : ""}" data-t="${t}">${UI.esc(t)}</span>`).join("");

      document.getElementById("req-content").innerHTML = `
        <div class="card">
          ${canConfirm ? "" : UI.notice("warning", "要求基线确认暂不可用", `存在未处理阻断项：${b.blockers.join("、")}${b.highUnconfirmed.length ? "；高风险未确认：" + b.highUnconfirmed.join("、") : ""}。需全部处理后方可确认（文档 5.7 第一个人工关口）。`)}
          <div class="tabs">${tabs}</div>
          <div class="toolbar">
            <button class="btn btn-sm" id="batch-confirm">批量确认普通项</button>
            <span class="spacer"></span>
            <span class="text-sm secondary">已选 <span id="sel-count" class="num">0</span> 项</span>
          </div>
          <div class="table-wrap"><table class="grid">
            <thead><tr><th></th><th>编号</th><th>类型</th><th>原文摘要</th><th>来源页码</th><th>采购包</th><th>风险等级</th><th>处理状态</th><th>责任人</th><th>响应章节</th><th>证据状态</th><th>操作</th></tr></thead>
            <tbody>${rows || UI.emptyState("该分类下暂无要求")}</tbody>
          </table></div>
        </div>`;

      document.querySelectorAll(".tab").forEach((t) => t.onclick = () => { activeType = t.dataset.t; render(); });
      document.querySelectorAll(".row-check").forEach((c) => c.onchange = () => {
        selected = [...document.querySelectorAll(".row-check:checked")].map((x) => x.value);
        document.getElementById("sel-count").textContent = selected.length;
      });
      document.getElementById("batch-confirm").onclick = () => {
        if (!selected.length) { UI.toast("请先勾选普通项", "warning"); return; }
        UI.toast("已批量确认 " + selected.length + " 个普通项", "success");
      };
      document.querySelectorAll("[data-act]").forEach((btn) => btn.onclick = () => {
        const r = data.items.find((x) => x.id === btn.dataset.id);
        const act = btn.dataset.act;
        if (act === "view") UI.drawer({ title: "原文：" + r.no, body: `<dl class="kv"><dt>类型</dt><dd>${UI.esc(r.type)}</dd><dt>原文摘要</dt><dd>${UI.esc(r.summary)}</dd><dt>来源页码</dt><dd class="num">p${r.page}</dd><dt>采购包</dt><dd>${UI.esc(r.package)}</dd></dl>`, footer: `<button class="btn" onclick="UI.closeDrawer()">关闭</button>` });
        else if (act === "edit") UI.modal({ title: "人工修改：" + r.no, body: `<div class="field"><label>原文摘要</label><textarea class="control">${UI.esc(r.summary)}</textarea></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已保存修改','success')">保存</button>` });
        else if (act === "split") UI.modal({ title: "拆分混合要求：" + r.no, body: `<p class="text-sm secondary">将混合要求拆分为多条独立要求。</p><div class="field"><label>拆分结果（每行一条）</label><textarea class="control" placeholder="条目一\n条目二"></textarea></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已拆分','success')">确认拆分</button>` });
        else if (act === "merge") UI.toast("已合并重复要求", "success");
        else if (act === "pending") UI.toast("已标记为待确认", "info");
        else if (act === "owner") UI.modal({ title: "分配责任人：" + r.no, body: `<div class="field"><label>责任人</label><select class="control"><option>资料管理员</option><option>技术方案人员</option><option>商务/报价人员</option><option>标书编写人</option></select></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已分配责任人','success')">保存</button>` });
        else if (act === "conflict") UI.drawer({ title: "冲突查看：" + r.no, body: `<div class="notice warning">${Icons.alert({ size: 14 })}<span class="nt-body"><span class="nt-title">未发现直接冲突</span><span class="nt-desc">该要求与其他条目暂无逻辑冲突。</span></span></div>`, footer: `<button class="btn" onclick="UI.closeDrawer()">关闭</button>` });
      });
    };
    render();

    const cb = document.getElementById("confirm-baseline");
    cb.disabled = !canConfirm;
    cb.onclick = () => {
      if (!canConfirm) { UI.toast("存在未处理阻断项或高风险未确认", "error"); return; }
      UI.modal({ title: "要求基线确认（第一个人工关口）", body: UI.notice("warning", "确认后要求基线将锁定", "确认后依赖该基线的响应规划与章节生成方可进行。无证据要求不得显示肯定结论。"), footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('要求基线已确认','success')">确认基线</button>` });
    };
  }).catch((err) => UI.handleError(err));
};

/* ---------------- 响应规划 /projects/{id}/response-plan（文档 5.8） ---------------- */
window.Views["response-plan"] = (container, id) => {
  container.innerHTML = UI.topbar("响应规划", "响应规划",
    `<button class="btn btn-primary btn-sm" id="confirm-plan">${Icons.gate({ size: 14 })} 响应规划确认</button>`) +
    `<div id="plan-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + `/projects/${id}/response-plan`).then((data) => {
    const render = () => {
      const matrixRows = data.matrix.map((m) => `<tr>
        <td class="num">${UI.esc(m.requirementNo)}</td>
        <td>${UI.esc(m.response)}</td>
        <td>${m.evidence === "证据待补充" ? `<span class="badge danger-high">证据待补充</span>` : UI.esc(m.evidence)}</td>
        <td>${UI.esc(m.owner)}</td>
        <td>${UI.esc(m.status)}</td>
        <td>${UI.esc(m.scoreCover)}</td>
        <td>${UI.esc(m.historyDiff)}</td>
        <td>
          <button class="btn btn-sm" data-act="bind" data-id="${m.id}">绑定证据</button>
          <button class="btn btn-sm" data-act="section" data-id="${m.id}">指定章节</button>
          <button class="btn btn-sm" data-act="miss" data-id="${m.id}">标记缺失</button>
        </td>
      </tr>`).join("");

      document.getElementById("plan-content").innerHTML = `
        <div class="card">
          ${data.baseline.confirmed ? UI.notice("success", "响应规划基线已确认", "未确认规划不得进入正式章节生成（文档 5.8 第二个人工关口）。") : UI.notice("warning", "响应规划尚未确认", "确认后方可生成正式章节草稿。")}
          <div class="toolbar">
            <button class="btn btn-sm" id="gen-plan">${Icons.refresh({ size: 13 })} 生成响应规划（异步任务）</button>
            <button class="btn btn-sm" id="view-coverage">查看评分覆盖</button>
            <span class="spacer"></span>
            <span class="text-sm secondary">响应矩阵 ${data.matrix.length} 项</span>
          </div>
          <div class="table-wrap"><table class="grid">
            <thead><tr><th>要求编号</th><th>响应方式</th><th>证据用途</th><th>责任人</th><th>任务状态</th><th>评分覆盖</th><th>历史参考差异</th><th>操作</th></tr></thead>
            <tbody>${matrixRows}</tbody>
          </table></div>
        </div>

        <div class="card">
          <div class="card-head"><h2>历史参考项目及差异</h2></div>
          <div class="table-wrap"><table class="grid">
            <thead><tr><th>参考项目</th><th>差异说明</th></tr></thead>
            <tbody>${data.references.map((r) => `<tr><td>${UI.esc(r.name)}</td><td>${UI.esc(r.diff)}</td></tr>`).join("")}</tbody>
          </table></div>
        </div>`;

      document.getElementById("gen-plan").onclick = () => {
        ApiClient.createTask("响应规划生成").then((t) => UI.toast("已创建任务 " + t.task_run_id + "（轮询中）", "info"));
      };
      document.getElementById("view-coverage").onclick = () => {
        UI.drawer({ title: "评分覆盖", body: data.matrix.map((m) => `<div class="card" style="padding:10px 12px"><strong>${UI.esc(m.requirementNo)}</strong> · ${UI.esc(m.scoreCover)}</div>`).join(""), footer: `<button class="btn" onclick="UI.closeDrawer()">关闭</button>` });
      };
      document.querySelectorAll("[data-act]").forEach((btn) => btn.onclick = () => {
        const act = btn.dataset.act;
        if (act === "bind") UI.modal({ title: "绑定企业证据", body: `<div class="field"><label>企业证据</label><select class="control"><option>运维SLA模板 v1</option><option>信息安全服务资质</option><option>本地服务团队名单</option></select></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已绑定证据','success')">绑定</button>` });
        else if (act === "section") UI.modal({ title: "指定章节与负责人", body: `<div class="field"><label>章节</label><select class="control"><option>第2章 投标人资格</option><option>第4章 技术方案</option></select></div><div class="field"><label>负责人</label><input class="control" placeholder="责任人" /></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已指定','success')">保存</button>` });
        else if (act === "miss") UI.toast("已标记缺失证据", "warning");
      });
    };
    render();

    document.getElementById("confirm-plan").onclick = () => {
      if (!data.baseline.confirmed) {
        UI.modal({ title: "响应规划确认（第二个人工关口）", body: UI.notice("warning", "确认后将锁定规划", "无确认的规划不得进入正式章节生成。"), footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('响应规划已确认','success');location.reload()">确认规划</button>` });
      } else {
        UI.toast("响应规划基线已确认", "info");
      }
    };
  }).catch((err) => UI.handleError(err));
};
