/* 视图：企业资料库 / 模板与规则 / 系统管理
   对应文档 5.13–5.15（P1 页面）。 */

/* ---------------- 企业资料库 /knowledge（文档 5.13） ---------------- */
App.register("knowledge", (container) => {
  container.innerHTML = UI.topbar("企业资料库", "企业资料库",
    `<button class="btn btn-primary btn-sm" id="up-mat">${Icons.upload({ size: 14 })} 上传资料</button>`) +
    `<div id="k-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + "/knowledge").then((list) => {
    const stateBadge = (s) => {
      if (s === "可用") return `<span class="badge success"><span class="dot solid"></span>可用证据</span>`;
      if (s === "EXPIRED") return `<span class="badge danger-block"><span class="dot solid"></span>已过期</span>`;
      if (s === "主体不符") return `<span class="badge danger-high"><span class="dot solid"></span>主体不符</span>`;
      if (s === "范围不符") return `<span class="badge danger-high"><span class="dot solid"></span>范围不符</span>`;
      if (s === "无权限") return `<span class="badge neutral"><span class="dot solid"></span>无权限</span>`;
      return `<span class="badge neutral">${UI.esc(s)}</span>`;
    };
    const rows = list.map((k) => {
      const usable = k.state === "可用";
      return `<tr>
        <td>${UI.esc(k.name)}</td>
        <td>${UI.esc(k.category)}</td>
        <td>${UI.esc(k.subject)}</td>
        <td class="num">${UI.fmtDate(k.validTo)}</td>
        <td>${UI.esc(k.scope)}</td>
        <td>${UI.esc(k.permission)}</td>
        <td>${UI.esc(k.source)}</td>
        <td>${stateBadge(k.state)}</td>
        <td class="${usable ? "" : "risk-high"}">${UI.esc(k.note)}</td>
        <td>${usable ? `<button class="btn btn-sm" data-use="${k.id}">设为可用证据</button>` : `<span class="muted text-xs">不可进入可用证据</span>`}</td>
      </tr>`;
    }).join("");

    document.getElementById("k-content").innerHTML = `
      <div class="card">
        ${UI.notice("warning", "资料可用性边界", "过期、主体不符、范围不符或无权限资料必须明确标识，不能进入“可用证据”状态。")}
        <div class="toolbar">
          <div class="search">${Icons.search({ size: 15 })}<input id="k-search" placeholder="搜索资料名称 / 主体" /></div>
          <span class="spacer"></span><span class="text-sm secondary">共 ${list.length} 项</span>
        </div>
        <div class="table-wrap"><table class="grid">
          <thead><tr><th>资料名称</th><th>类别</th><th>主体</th><th>有效期至</th><th>适用范围</th><th>权限等级</th><th>来源</th><th>状态</th><th>说明</th><th>操作</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      </div>`;

    document.getElementById("k-search").addEventListener("input", (e) => {
      const q = e.target.value.trim().toLowerCase();
      document.querySelectorAll("#k-content tbody tr").forEach((tr, i) => {
        const k = list[i];
        tr.style.display = (!q || k.name.toLowerCase().includes(q) || k.subject.toLowerCase().includes(q)) ? "" : "none";
      });
    });
    document.querySelectorAll("[data-use]").forEach((b) => b.onclick = () => UI.toast("已设为可用证据", "success"));
    document.getElementById("up-mat").onclick = () => UI.modal({ title: "上传资料", body: `<div class="field"><label>文件</label><input type="file" class="control" /></div><div class="field"><label>主体</label><input class="control" placeholder="资料主体" /></div><div class="field"><label>有效期</label><input class="control" type="date" /></div><div class="field"><label>适用范围</label><input class="control" placeholder="适用范围" /></div><div class="field"><label>权限等级</label><select class="control"><option>公开</option><option>项目内</option><option>受限</option></select></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已上传并进入版本维护','success')">上传</button>` });
  }).catch((err) => UI.handleError(err));
});

/* ---------------- 模板与规则 /templates-rules（文档 5.14） ---------------- */
App.register("templatesRules", (container) => {
  container.innerHTML = UI.topbar("模板与规则", "模板与规则", "") +
    `<div id="tr-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + "/templates-rules").then((data) => {
    const stateBadge = (s) => {
      const map = { 启用: "success", 测试中: "warning", 草稿: "neutral", 停用: "neutral" };
      return `<span class="badge ${map[s] || "neutral"}"><span class="dot solid"></span>${UI.esc(s)}</span>`;
    };
    document.getElementById("tr-content").innerHTML = `
      <div class="card">
        <div class="card-head"><h2>模板</h2><span class="sub">状态：草稿 / 测试中 / 启用 / 停用</span></div>
        <div class="table-wrap"><table class="grid"><thead><tr><th>模板名称</th><th>版本</th><th>状态</th><th>更新时间</th></tr></thead>
        <tbody>${data.templates.map((t) => `<tr><td>${UI.esc(t.name)}</td><td class="num">${UI.esc(t.version)}</td><td>${stateBadge(t.state)}</td><td class="num">${UI.fmtDate(t.updated)}</td></tr>`).join("")}</tbody></table></div>
        ${UI.notice("info", "版本化规则", "规则集需版本化；启用新版本不改写历史项目使用的版本。")}
      </div>
      <div class="card">
        <div class="card-head"><h2>规则集</h2></div>
        <div class="table-wrap"><table class="grid"><thead><tr><th>规则集</th><th>版本</th><th>状态</th><th>说明</th></tr></thead>
        <tbody>${data.ruleSets.map((r) => `<tr><td>${UI.esc(r.name)}</td><td class="num">${UI.esc(r.version)}</td><td>${stateBadge(r.state)}</td><td class="text-sm secondary">${UI.esc(r.note)}</td></tr>`).join("")}</tbody></table></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>业务词表</h2></div>
        <div class="table-wrap"><table class="grid"><thead><tr><th>术语</th><th>定义</th></tr></thead>
        <tbody>${data.glossary.map((g) => `<tr><td>${UI.esc(g.term)}</td><td>${UI.esc(g.def)}</td></tr>`).join("")}</tbody></table></div>
      </div>`;
  }).catch((err) => UI.handleError(err));
});

/* ---------------- 系统管理 /admin（文档 5.15） ---------------- */
App.register("admin", (container) => {
  container.innerHTML = UI.topbar("系统管理", "系统管理", "") +
    `<div id="ad-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + "/admin/users").then((data) => {
    let tab = "users";
    const render = () => {
      let body = "";
      if (tab === "users") {
        body = `<div class="toolbar"><button class="btn btn-sm btn-primary" id="add-user">${Icons.plus({ size: 13 })} 创建账号</button><span class="spacer"></span><span class="text-sm secondary">账号创建、启停、管理员重置密码、Session 撤销。</span></div>
          <div class="table-wrap"><table class="grid"><thead><tr><th>姓名</th><th>账号</th><th>角色</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>${data.users.map((u) => `<tr><td>${UI.esc(u.name)}</td><td class="num">${UI.esc(u.account)}</td><td>${UI.esc(u.role)}</td><td>${u.enabled ? `<span class="badge success"><span class="dot solid"></span>启用</span>` : `<span class="badge neutral"><span class="dot solid"></span>禁用</span>`}</td><td><button class="btn btn-sm" data-toggle="${u.id}">${u.enabled ? "禁用" : "启用"}</button><button class="btn btn-sm" data-reset="${u.id}">重置密码</button><button class="btn btn-sm" data-revoke="${u.id}">撤销 Session</button></td></tr>`).join("")}</tbody></table></div>`;
      } else if (tab === "services") {
        body = `<div class="table-wrap"><table class="grid"><thead><tr><th>服务</th><th>健康状态</th><th>队列数量</th><th>最近失败</th></tr></thead>
          <tbody>${data.services.map((s) => `<tr><td>${UI.esc(s.name)}</td><td>${s.health.includes("失败") ? `<span class="badge danger-high"><span class="dot solid"></span>${UI.esc(s.health)}</span>` : `<span class="badge success"><span class="dot solid"></span>${UI.esc(s.health)}</span>`}</td><td class="num">${s.queue}</td><td class="num">${UI.esc(s.lastFail)}</td></tr>`).join("")}</tbody></table></div>
          <div class="row" style="margin-top:10px;gap:8px"><button class="btn btn-sm">查看容量</button><button class="btn btn-sm">备份管理</button></div>`;
      } else if (tab === "runtime") {
        body = `<div class="card-grid grid-4"><div class="stat"><div class="label">健康服务</div><div class="value num">${data.services.filter((s) => !s.health.includes("失败")).length}</div></div><div class="stat"><div class="label">异常服务</div><div class="value num" style="color:var(--danger-high)">${data.services.filter((s) => s.health.includes("失败")).length}</div></div><div class="stat"><div class="label">队列任务</div><div class="value num">${data.services.reduce((a, s) => a + s.queue, 0)}</div></div><div class="stat"><div class="label">失败任务</div><div class="value num">1</div></div></div>`;
      } else {
        body = `<div class="card"><div class="card-head"><h2>安全与审计</h2></div>
          <div class="table-wrap"><table class="grid"><thead><tr><th>类型</th><th>说明</th><th>时间</th></tr></thead>
          <tbody>${data.security.map((s) => `<tr><td>${UI.esc(s.type)}</td><td>${UI.esc(s.desc)}</td><td class="num">${UI.esc(s.time)}</td></tr>`).join("")}</tbody></table></div>
          <div class="notice info" style="margin-top:10px">${Icons.info({ size: 14 })}<span class="nt-body"><span class="nt-title">API Key 不展示明文</span><span class="nt-desc">系统不建设 Agent / Skill / MCP 的动态安装或管理页面（文档 5.15）。</span></span></div>
        </div>`;
      }
      const tabs = ["users", "services", "runtime", "security"].map((t) => {
        const label = { users: "用户与权限", services: "模型与外部服务", runtime: "运行状态", security: "安全与审计" }[t];
        return `<span class="tab ${tab === t ? "active" : ""}" data-t="${t}">${label}</span>`;
      }).join("");
      document.getElementById("ad-content").innerHTML = `<div class="card"><div class="tabs">${tabs}</div>${body}</div>`;
      document.querySelectorAll(".tab[data-t]").forEach((t) => t.onclick = () => { tab = t.dataset.t; render(); });
      document.querySelectorAll("[data-toggle]").forEach((b) => b.onclick = () => UI.toast("已切换账号启停状态", "success"));
      document.querySelectorAll("[data-reset]").forEach((b) => b.onclick = () => UI.modal({ title: "管理员重置密码", body: `<div class="field"><label>新密码</label><input class="control" type="password" placeholder="设置新密码" /></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('已重置密码','success')">重置</button>` }));
      document.querySelectorAll("[data-revoke]").forEach((b) => b.onclick = () => UI.toast("已撤销该用户 Session", "success"));
      const add = document.getElementById("add-user"); if (add) add.onclick = () => UI.modal({ title: "创建账号", body: `<div class="field"><label>姓名</label><input class="control" /></div><div class="field"><label>账号</label><input class="control" /></div><div class="field"><label>角色</label><select class="control">${Object.values(ROLES).map((r) => `<option>${UI.esc(r)}</option>`).join("")}</select></div>`, footer: `<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast('账号已创建','success')">创建</button>` });
    };
    render();
  }).catch((err) => UI.handleError(err));
});
