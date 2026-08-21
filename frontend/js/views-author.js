/* 视图：标书编制 / 审核与风险 / 交接与递交 / 项目记录
   对应文档 5.9–5.12。 */

/* ---------------- 标书编制 /projects/{id}/authoring（文档 5.9） ---------------- */
window.Views.authoring = (container, id) => {
  container.innerHTML = UI.topbar("标书编制", "标书编制",
    `<button class="btn btn-primary btn-sm" id="gen-draft">${Icons.refresh({ size: 14 })} 基于响应规划生成草稿</button>
     <button class="btn btn-primary btn-sm" id="confirm-draft">${Icons.gate({ size: 14 })} 章节初稿确认</button>`) +
    `<div id="auth-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + `/projects/${id}/sections`).then((sections) => {
    const detail = MockData.projectDetail[id];
    const active = detail.authoring.active;
    const draft = detail.authoring.draftBaseline;

    const render = () => {
      const left = sections.map((s) => `<div class="col-item ${s.id === active.id ? "active" : ""}" data-id="${s.id}">
        <div class="ci-title">${UI.esc(s.title)} ${riskBadge(s.risk)}</div>
        <div class="ci-meta">负责人：${UI.esc(s.owner)} · ${UI.esc(s.status)}</div>
        <div class="ci-row"><span>完成度 ${s.progress}%</span><span>${s.locked}/${s.blocks} 锁定</span></div>
        <div class="progress" style="margin-top:4px"><span style="width:${s.progress}%"></span></div>
      </div>`).join("");

      const mid = `
        <h3>${UI.esc(active.title)} · 内容块</h3>
        ${active.blocks.map((b) => `<div class="card" style="padding:12px 14px;margin-bottom:10px">
          <div class="row between"><strong>${UI.esc(b.title)}</strong>
            ${b.locked ? `<span class="badge neutral">${Icons.lock({ size: 13 })} 已锁定（人工修改）</span>` : `<span class="badge info">未锁定</span>`}
          </div>
          <div class="text-xs muted" style="margin:4px 0">类型：${UI.esc(b.type)} · 版本 ${UI.esc(b.version)}</div>
          <div style="margin:6px 0">${UI.esc(b.text)}</div>
          ${b.locked ? `<div class="notice info" style="margin:6px 0">${Icons.lock({ size: 13 })}<span class="nt-body"><span class="nt-title">人工锁定内容</span><span class="nt-desc">重生成只产生新版本，不会静默覆盖此处人工结论。</span></span></div>` : `<div class="row" style="gap:8px"><button class="btn btn-sm" data-rewrite="${b.id}">定向重写</button><button class="btn btn-sm" data-lock="${b.id}">锁定</button><button class="btn btn-sm" data-diff="${b.id}">查看差异</button></div>`}
        </div>`).join("")}
        <div class="toolbar">
          <button class="btn btn-sm" id="gen-one">${Icons.spark || Icons.refresh({ size: 13 })} 单章节生成</button>
          <button class="btn btn-sm" id="save-draft">保存草稿（乐观锁）</button>
          <button class="btn btn-sm" id="submit-review">提交初稿审核</button>
        </div>`;

      const right = `
        <h3>要求 / 评分项</h3>
        ${active.references.filter((r) => r.type === "要求" || r.type === "评分项").map((r) => `<div class="col-item"><div class="ci-title">${UI.esc(r.type)}</div><div class="ci-meta">${UI.esc(r.text)}</div><div class="ci-row"><span>${UI.esc(r.source)}</span></div></div>`).join("")}
        <h3 style="margin-top:12px">企业证据 / 历史参考</h3>
        ${active.references.filter((r) => r.type === "企业证据" || r.type === "历史参考").map((r) => `<div class="col-item"><div class="ci-title">${UI.esc(r.type)}</div><div class="ci-meta">${UI.esc(r.text)}</div><div class="ci-row"><span>${UI.esc(r.source)}</span></div></div>`).join("")}
        <h3 style="margin-top:12px">引用来源 / 生成记录</h3>
        <ul class="timeline">
          ${active.generation.map((g) => `<li><div class="tl-time num">${UI.fmtDateTime(g.time)}</div><div class="tl-title">${UI.esc(g.by)}</div><div class="tl-desc">版本 ${UI.esc(g.version)}</div></li>`).join("")}
        </ul>`;

      document.getElementById("auth-content").innerHTML = `
        <div class="card">
          ${draft.confirmed ? UI.notice("success", "章节初稿已确认（第三个人工关口）", "确认后可进入审核与风险流程。") : UI.notice("info", "标书编制工作台", "左侧章节目录；中间内容块编辑；右侧要求、证据、引用与生成记录。人工锁定内容不会被静默覆盖。")}
          <div class="three-col" style="margin-top:14px">
            <div class="col-panel"><h3>章节目录</h3>${left}</div>
            <div class="col-panel">${mid}</div>
            <div class="col-panel">${right}</div>
          </div>
        </div>`;

      document.querySelectorAll(".col-item[data-id]").forEach((el) => el.onclick = () => {
        const s = sections.find((x) => x.id === el.dataset.id);
        UI.toast("切换到：" + s.title, "info");
      });
      document.querySelectorAll("[data-rewrite]").forEach((b) => b.onclick = () => {
        const blk = active.blocks.find((x) => x.id === b.dataset.rewrite);
        UI.modal({ title: "定向重写：" + blk.title, body: `<div class="field"><label>新内容</label><textarea class="control">${UI.esc(blk.text)}</textarea></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已生成新版本，请确认差异','success')">重写</button>` });
      });
      document.querySelectorAll("[data-lock]").forEach((b) => b.onclick = () => UI.toast("已锁定内容块（人工修改受保护）", "success"));
      document.querySelectorAll("[data-diff]").forEach((b) => b.onclick = () => {
        UI.drawer({ title: "新旧版本差异", body: `<div class="card" style="padding:10px 12px"><div class="diff-del">- 旧版本内容（v1）</div></div><div class="card" style="padding:10px 12px"><div class="diff-add">+ 新版本内容（v2，人工锁定后重写）</div></div><p class="text-sm secondary">重生成只产生新版本，必须展示差异并由用户确认。</p>`, footer: `<button class="btn" onclick="UI.closeDrawer()">关闭</button>` });
      });
      document.getElementById("gen-one").onclick = () => { ApiClient.createTask("章节草稿生成").then((t) => UI.toast("已创建任务 " + t.task_run_id, "info")); };
      document.getElementById("save-draft").onclick = () => {
        ApiClient.post(ApiClient.BASE + `/projects/${id}/sections`, { version: 2 }, { idempotencyKey: "idem-save-" + Date.now(), version: 2 }).then(() => UI.toast("草稿已保存（乐观锁校验通过）", "success")).catch((e) => UI.handleError(e));
      };
      document.getElementById("submit-review").onclick = () => UI.toast("已提交初稿审核", "success");
    };
    render();

    document.getElementById("gen-draft").onclick = () => { ApiClient.createTask("章节草稿生成").then((t) => UI.toast("已创建任务 " + t.task_run_id, "info")); };
    document.getElementById("confirm-draft").onclick = () => {
      UI.modal({ title: "章节初稿确认（第三个人工关口）", body: UI.notice("warning", "确认后将进入审核", "确认后提交审核与风险流程。未确认不得进入审核结果确认与交接。"), footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('章节初稿已确认','success')">确认初稿</button>` });
    };
  }).catch((err) => UI.handleError(err));
};

/* ---------------- 审核与风险 /projects/{id}/reviews（文档 5.10） ---------------- */
window.Views.reviews = (container, id) => {
  container.innerHTML = UI.topbar("审核与风险", "审核与风险",
    `<button class="btn btn-primary btn-sm" id="confirm-review">${Icons.gate({ size: 14 })} 审核结果确认</button>`) +
    `<div id="rev-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + `/projects/${id}/reviews`).then((data) => {
    let tab = "summary";

    const render = () => {
      const issueRows = data.issues.map((i) => `<tr>
        <td>${UI.esc(i.domain)}</td>
        <td>${UI.esc(i.type)}</td>
        <td>${riskBadge(i.risk)}</td>
        <td class="td-clamp">${UI.esc(i.desc)}</td>
        <td class="num">${UI.esc(i.sourceReq)}</td>
        <td>${UI.esc(i.impactSection)}</td>
        <td>${UI.esc(i.owner)}</td>
        <td>${i.status === "已关闭" ? `<span class="badge success"><span class="dot solid"></span>已关闭</span>` : i.status === "已退回" ? `<span class="badge danger-high"><span class="dot solid"></span>已退回</span>` : i.status === "复核中" ? `<span class="badge warning"><span class="dot solid"></span>复核中</span>` : `<span class="badge neutral"><span class="dot solid"></span>${UI.esc(i.status)}</span>`}</td>
        <td class="num">R${i.round}</td>
        <td><button class="btn btn-sm" data-fix="${i.id}">提交修改</button><button class="btn btn-sm" data-review="${i.id}">复核</button><button class="btn btn-sm" data-reopen="${i.id}">重开</button></td>
      </tr>`).join("");

      const riskRows = data.risks.map((r) => `<tr>
        <td class="num">${UI.esc(r.requirement)}</td>
        <td>${riskBadge(r.level)}</td>
        <td>${UI.esc(r.desc)}</td>
        <td>${r.acceptance ? `<span class="badge neutral">已接受</span>` : r.exemptBy ? `<span class="badge warning">已豁免（${UI.esc(r.exemptBy)}）</span>` : `<span class="badge danger-high">未处理</span>`}</td>
        <td>${r.acceptance || r.exemptBy ? "—" : `<button class="btn btn-sm" data-accept="${r.requirement}">风险接受</button><button class="btn btn-sm" data-exempt="${r.requirement}">审批豁免</button>`}</td>
      </tr>`).join("");

      const consRows = data.consistency.map((c) => `<tr><td>${UI.esc(c.area)}</td><td>${UI.esc(c.result)}</td><td>${UI.esc(c.detail)}</td><td>${UI.esc(c.status)}</td></tr>`).join("");

      let body = "";
      if (tab === "summary") {
        body = `<div class="card-grid grid-4" style="margin-bottom:14px">
          <div class="stat"><div class="label">问题总数</div><div class="value num">${data.summary.total}</div></div>
          <div class="stat"><div class="label">待处理</div><div class="value num">${data.summary.open}</div></div>
          <div class="stat"><div class="label">高风险</div><div class="value num" style="color:var(--danger-high)">${data.summary.high}</div></div>
          <div class="stat"><div class="label">阻断</div><div class="value num" style="color:var(--danger-block)">${data.summary.block}</div></div>
        </div>
        ${data.summary.block > 0 ? UI.notice("error", "存在阻断风险", "阻断风险必须解决或由授权人员豁免，否则不得建立有效交接基线（文档 5.10 规则）。") : UI.notice("success", "无未解决阻断风险", "可进入审核结果确认。")}
        <div class="card"><div class="card-head"><h2>审核问题概览</h2></div>
          <div class="table-wrap"><table class="grid"><thead><tr><th>审核域</th><th>问题类型</th><th>风险</th><th>描述</th><th>来源要求</th><th>影响章节</th><th>责任人</th><th>状态</th><th>轮次</th><th>操作</th></tr></thead><tbody>${issueRows}</tbody></table></div>
        </div>`;
      } else if (tab === "issues") {
        body = `<div class="toolbar"><button class="btn btn-sm" id="create-review">${Icons.plus({ size: 13 })} 创建审核与风险复核任务</button><span class="spacer"></span><span class="text-sm secondary">编写人不能关闭自己提交的问题；Agent 不能自动关闭问题。</span></div>
          <div class="table-wrap"><table class="grid"><thead><tr><th>审核域</th><th>问题类型</th><th>风险</th><th>描述</th><th>来源要求</th><th>影响章节</th><th>责任人</th><th>处理状态</th><th>轮次</th><th>操作</th></tr></thead><tbody>${issueRows}</tbody></table></div>`;
        document.getElementById("create-review").onclick = () => { ApiClient.createTask("审核与风险复核").then((t) => UI.toast("已创建任务 " + t.task_run_id, "info")); };
      } else if (tab === "risks") {
        body = `<div class="table-wrap"><table class="grid"><thead><tr><th>来源要求</th><th>风险等级</th><th>说明</th><th>接受/豁免状态</th><th>操作</th></tr></thead><tbody>${riskRows}</tbody></table></div>`;
      } else {
        body = `${UI.notice("info", "一致性检查", "修改后必须重新审核；当前版本存在未复核变更时，不允许进入交接。")}
          <div class="table-wrap"><table class="grid"><thead><tr><th>检查域</th><th>结果</th><th>详情</th><th>状态</th></tr></thead><tbody>${consRows}</tbody></table></div>`;
      }

      const tabs = ["summary", "issues", "risks", "consistency"].map((t) => {
        const label = { summary: "审核总览", issues: "审核问题", risks: "风险清单", consistency: "一致性检查" }[t];
        return `<span class="tab ${tab === t ? "active" : ""}" data-t="${t}">${label}</span>`;
      }).join("");

      document.getElementById("rev-content").innerHTML = `
        <div class="card">
          <div class="tabs">${tabs}</div>
          ${body}
        </div>`;

      document.querySelectorAll(".tab[data-t]").forEach((t) => t.onclick = () => { tab = t.dataset.t; render(); });
      document.querySelectorAll("[data-fix]").forEach((b) => b.onclick = () => {
        const i = data.issues.find((x) => x.id === b.dataset.fix);
        UI.modal({ title: "提交结构化修改：" + i.id, body: `<div class="field"><label>修改说明</label><textarea class="control">${UI.esc(i.desc)}</textarea></div><div class="field"><label>处理记录</label><input class="control" placeholder="追加处理记录" /></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已提交结构化修改，待复核','success')">提交</button>` });
      });
      document.querySelectorAll("[data-review]").forEach((b) => b.onclick = () => UI.toast("已复核（修改后须重新审核）", "success"));
      document.querySelectorAll("[data-reopen]").forEach((b) => b.onclick = () => UI.toast("已重新打开问题", "info"));
      document.querySelectorAll("[data-accept]").forEach((b) => b.onclick = () => {
        UI.modal({ title: "记录风险接受：" + b.dataset.accept, body: `<div class="field"><label>接受理由</label><textarea class="control" placeholder="记录风险接受理由"></textarea></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已记录风险接受','success')">确认接受</button>` });
      });
      document.querySelectorAll("[data-exempt]").forEach((b) => b.onclick = () => {
        UI.modal({ title: "审批风险豁免：" + b.dataset.exempt, body: UI.notice("warning", "仅授权人员可豁免", "阻断风险必须解决或由授权人员豁免。") + `<div class="field"><label>豁免理由</label><textarea class="control" placeholder="审批豁免理由"></textarea></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已审批豁免','success')">确认豁免</button>` });
      });
    };
    render();

    const cb = document.getElementById("confirm-review");
    cb.onclick = () => {
      if (data.summary.block > 0) { UI.toast("存在未解决阻断风险，审核结果确认不可用", "error"); return; }
      UI.modal({ title: "审核结果确认（第四个人工关口）", body: UI.notice("warning", "确认后将允许进入交接", "当前版本存在未复核变更时不允许进入交接。"), footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('审核结果已确认','success')">确认结果</button>` });
    };
  }).catch((err) => UI.handleError(err));
};

/* ---------------- 交接与递交 /projects/{id}/handover（文档 5.11） ---------------- */
window.Views.handover = (container, id) => {
  container.innerHTML = UI.topbar("交接与递交", "交接与递交", "") +
    `<div id="ho-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + `/projects/${id}/handover-packages`).then((ho) => {
    const render = () => {
      const chain = ho.chain.map((c, i) => {
        const cls = c.state === "done" ? "done" : c.state === "block" ? "block" : c.state === "active" ? "active" : "";
        const ico = c.state === "done" ? Icons.check({ size: 13 }) : c.state === "block" ? Icons.alert({ size: 13 }) : "•";
        return `<li class="${c.state === "block" ? "block" : ""}">
          <div class="tl-title">${ico} ${UI.esc(c.key)} ${c.state === "pending" ? `<span class="badge neutral">待处理</span>` : c.state === "block" ? `<span class="badge danger-block">未就绪</span>` : ""}</div>
          <div class="tl-desc">${UI.esc(c.note)}</div>
        </li>`;
      }).join("");

      const fileRows = ho.fileList.map((f) => `<tr><td>${UI.esc(f.name)}</td><td class="num">${UI.esc(f.hash)}</td><td>${f.export === "待生成" ? `<span class="badge warning">待生成</span>` : `<span class="badge success">已导出</span>`}</td></tr>`).join("");

      document.getElementById("ho-content").innerHTML = `
        <div class="card">
          ${ho.blockRisks > 0 || ho.unconfirmedGates.length ? UI.notice("error", "交接门禁未通过", `未解决阻断风险 ${ho.blockRisks} 项；未确认人工关口：${ho.unconfirmedGates.join("、")}。系统不自动连接或操作电子交易平台，只登记人工递交结果。`) : UI.notice("success", "交接门禁通过", "可生成交接包并登记人工递交。")}
          <div class="card-head"><h2>交接固定链路</h2></div>
          <ul class="timeline">${chain}</ul>
        </div>

        <div class="card">
          <div class="card-head"><h2>当前有效版本</h2></div>
          <dl class="kv">
            <dt>章节</dt><dd>${UI.esc(ho.versions.sections)}</dd>
            <dt>要求</dt><dd>${UI.esc(ho.versions.requirements)}</dd>
            <dt>报价</dt><dd>${UI.esc(ho.versions.quotation)}</dd>
            <dt>审核</dt><dd>${UI.esc(ho.versions.review)}</dd>
            <dt>文件</dt><dd>${UI.esc(ho.versions.files)}</dd>
          </dl>
        </div>

        <div class="card">
          <div class="card-head"><h2>交接包文件清单</h2><button class="btn btn-sm" id="gen-package">${Icons.file({ size: 13 })} 生成交接包</button></div>
          <div class="table-wrap"><table class="grid"><thead><tr><th>文件</th><th>文件哈希</th><th>导出状态</th></tr></thead><tbody>${fileRows || UI.emptyState("尚无交接包文件")}</tbody></table></div>
          <div class="row" style="margin-top:10px;gap:8px">
            <div class="field" style="flex:1"><label>接收责任人</label><input class="control" value="${UI.esc(ho.receiver)}" /></div>
            <div class="field" style="flex:1"><label>接收确认时间</label><input class="control" value="${ho.receivedAt || "—"}" readonly /></div>
          </div>
          <div class="toolbar" style="margin-top:10px">
            <button class="btn btn-sm" id="accept-pkg">${Icons.check({ size: 13 })} 确认接收</button>
            <button class="btn btn-sm" id="register-sub">${Icons.upload({ size: 13 })} 人工外部递交登记</button>
            <button class="btn btn-sm" id="upload-receipt">${Icons.download({ size: 13 })} 上传回执</button>
          </div>
          <div class="notice info" style="margin-top:8px">${Icons.info({ size: 14 })}<span class="nt-body"><span class="nt-title">人工递交状态</span><span class="nt-desc">${UI.esc(ho.submission.state)}；回执：${ho.submission.receipt ? UI.esc(ho.submission.receipt) : "未上传"}。系统不自动完成外部递交。</span></span></div>
        </div>`;

      document.getElementById("gen-package").onclick = () => { ApiClient.createTask("交接包生成").then((t) => UI.toast("已创建任务 " + t.task_run_id, "info")); };
      document.getElementById("accept-pkg").onclick = () => UI.modal({ title: "确认接收", body: UI.notice("info", "递交责任人确认接收", "确认后记录接收时间。"), footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已确认接收','success')">确认接收</button>` });
      document.getElementById("register-sub").onclick = () => UI.modal({ title: "人工外部递交登记", body: UI.notice("warning", "仅登记结果", "系统不连接或操作电子交易平台。") + `<div class="field"><label>递交方式</label><select class="control"><option>现场递交</option><option>邮寄递交</option><option>电子平台（人工操作）</option></select></div><div class="field"><label>递交时间</label><input class="control" type="datetime-local" /></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已登记人工递交','success')">登记</button>` });
      document.getElementById("upload-receipt").onclick = () => UI.modal({ title: "上传回执", body: `<div class="field"><label>回执文件</label><input type="file" class="control" /></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已上传回执','success')">上传</button>` });
    };
    render();
  }).catch((err) => UI.handleError(err));
};

/* ---------------- 项目记录 /projects/{id}/records（文档 5.12） ---------------- */
window.Views.records = (container, id) => {
  container.innerHTML = UI.topbar("项目记录", "项目记录",
    `<button class="btn btn-sm" id="export-audit">${Icons.download({ size: 14 })} 导出审计记录</button>`) +
    `<div id="rec-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + `/projects/${id}/timeline`).then((events) => {
    const types = [...new Set(events.map((e) => e.type))];
    let fType = "";

    const render = () => {
      const list = events.filter((e) => !fType || e.type === fType);
      document.getElementById("rec-content").innerHTML = `
        <div class="card">
          <div class="notice info">${Icons.info({ size: 14 })}<span class="nt-body"><span class="nt-title">历史记录不可覆盖</span><span class="nt-desc">记录只追加新事件。可按事件类型、操作者、时间、对象、版本筛选，并查看脱敏审计记录与导出。</span></span></div>
          <div class="toolbar">
            <select class="filter" id="f-type"><option value="">事件类型</option>${types.map((t) => `<option ${fType === t ? "selected" : ""}>${UI.esc(t)}</option>`).join("")}</select>
            <span class="spacer"></span><span class="text-sm secondary">共 ${list.length} 条事件</span>
          </div>
          <table class="grid"><thead><tr><th>时间</th><th>事件类型</th><th>操作者</th><th>对象</th><th>版本</th><th>说明</th></tr></thead>
          <tbody>${list.map((e) => `<tr><td class="num">${UI.fmtDateTime(e.time)}</td><td>${UI.esc(e.type)}</td><td>${UI.esc(e.actor)}</td><td>${UI.esc(e.object)}</td><td class="num">${UI.esc(e.version)}</td><td>${UI.esc(e.desc)}</td></tr>`).join("") || UI.emptyState("无匹配记录")}</tbody></table>
        </div>`;
      document.getElementById("f-type").onchange = (e) => { fType = e.target.value; render(); };
    };
    render();
    document.getElementById("export-audit").onclick = () => UI.toast("审计记录已导出（脱敏）", "success");
  }).catch((err) => UI.handleError(err));
};
