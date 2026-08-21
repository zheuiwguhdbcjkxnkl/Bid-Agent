/* 视图：登录 / 工作台 / 项目列表 / 新建项目 / 项目分发
   对应文档 5.1–5.5。严格按文档字段与边界实现，不新增 V2 能力。 */

/* 项目子页面注册表（由文档 4.2 项目内路由分发调用） */
window.Views = window.Views || {};

/* ---------------- 登录页 /login（文档 5.1） ---------------- */
App.register("login", (root) => {
  const PIPELINE = [
    { label: "采购文件解析", meta: "解析中" },
    { label: "要求与评分确认", meta: "待确认" },
    { label: "响应规划", meta: "待规划" },
    { label: "标书编制", meta: "编制中" },
    { label: "合规审核", meta: "待审核" },
  ];
  const pipelineHTML = PIPELINE.map((s, i) =>
    `<li class="lp-step">
       <span class="lp-dot">${i + 1}</span>
       <span class="lp-label">${UI.esc(s.label)}</span>
       <span class="lp-meta">${UI.esc(s.meta)}</span>
     </li>`).join("");

  root.innerHTML = `
    <div class="login-wrap">
      <aside class="login-aside">
        <div class="login-brandmark">
          <div class="seal">${Icons.documents({ size: 20 })}</div>
          <div class="org"><strong>投标文件智能编制与合规审核平台</strong>政府采购信息化服务项目</div>
        </div>
        <div>
          <div class="eyebrow">GOV BID · COMPLIANCE WORKBENCH</div>
          <h1 class="display">让每一份投标<br>都经得起合规审视</h1>
          <p class="lead">面向单采购包的闭环管理：从采购文件解析、要求确认、响应规划、标书编制到合规审核、交接与人工递交登记。</p>
          <div class="lp-head">
            <span class="lp-live"></span>
            <span class="lp-live-label">实时流程 · 您的项目正按此推进</span>
          </div>
          <ul class="lp-steps">${pipelineHTML}</ul>
        </div>
        <div class="foot">V1 · 后端前缀 /api/v1 · 服务端 Session 认证</div>
      </aside>
      <main class="login-main">
        <div class="login-card">
          <div class="lc-top">
            <div class="seal">${Icons.documents({ size: 18 })}</div>
            <div class="lc-org"><strong>投标文件合规审核平台</strong>安全登录</div>
          </div>
          <div id="login-form-wrap">
            <div class="eyebrow">账号登录</div>
            <div class="lc-title">登录</div>
            <div class="lc-sub">请使用分配的账号登录平台</div>
            <form id="login-form" class="form-grid" novalidate>
              <div class="field" id="f-account">
                <label for="account">账号<span class="req">*</span></label>
                <input class="control" id="account" name="account" type="text" autocomplete="username" placeholder="请输入账号" />
                <span class="err" id="e-account"></span>
              </div>
              <div class="field" id="f-password">
                <label for="password">密码<span class="req">*</span></label>
                <input class="control" id="password" name="password" type="password" autocomplete="current-password" placeholder="请输入密码" />
                <span class="err" id="e-password"></span>
              </div>
              <div id="login-msg"></div>
              <button class="btn btn-primary btn-block" type="submit">登录</button>
              <div class="login-security">
                ${Icons.lock({ size: 14 })}
                <span>登录使用服务端 Session Cookie，不使用前端持久化 JWT。账号密码仅用于身份校验。</span>
              </div>
              <div class="login-support">
                技术支持：信息化项目组 · 内线 8000<br>
                如遇账号禁用、限速或会话过期，请联系系统管理员。
              </div>
            </form>
          </div>
          <div id="login-progress-host" style="display:none"></div>
        </div>
      </main>
    </div>`;

  const form = document.getElementById("login-form");
  const wrap = document.getElementById("login-form-wrap");
  const host = document.getElementById("login-progress-host");
  const delay = (ms) => new Promise((r) => setTimeout(r, ms));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const account = document.getElementById("account").value.trim();
    const password = document.getElementById("password").value;
    document.getElementById("e-account").textContent = "";
    document.getElementById("e-password").textContent = "";
    document.getElementById("f-account").classList.remove("has-error");
    document.getElementById("f-password").classList.remove("has-error");
    document.getElementById("login-msg").innerHTML = "";
    if (!account) { document.getElementById("e-account").textContent = "请输入账号"; document.getElementById("f-account").classList.add("has-error"); return; }
    if (!password) { document.getElementById("e-password").textContent = "请输入密码"; document.getElementById("f-password").classList.add("has-error"); return; }

    /* 动态进度模拟：缓解等待焦虑，让“准备工作台”可见 */
    const STEPS = [
      { t: "安全身份认证", d: 460 },
      { t: "同步进行中项目", d: 520 },
      { t: "加载项目基线与要求", d: 520 },
      { t: "进入工作台", d: 420 },
    ];
    host.innerHTML = `
      <div class="login-progress">
        <div class="lp-ring"></div>
        <div class="lp-title">正在为您准备工作台</div>
        <div class="lp-bar"><span></span></div>
        <ul>${STEPS.map((s) => `<li><span class="mk"></span><span>${UI.esc(s.t)}</span></li>`).join("")}</ul>
      </div>`;
    wrap.style.display = "none";
    host.style.display = "block";
    const lis = Array.from(host.querySelectorAll("li"));
    const bar = host.querySelector(".lp-bar > span");
    const loginPromise = ApiClient.login(account, password);

    try {
      for (let i = 0; i < STEPS.length; i++) {
        lis[i].classList.add("active");
        bar.style.width = Math.round(((i + 1) / STEPS.length) * 100) + "%";
        await delay(STEPS[i].d);
        lis[i].classList.remove("active");
        lis[i].classList.add("done");
        lis[i].querySelector(".mk").innerHTML = Icons.check({ size: 11 });
      }
      const res = await loginPromise;
      if (res.mustChangePassword) {
        host.innerHTML = `<div class="login-progress">
          <div class="lp-title" style="margin-bottom:12px">需要修改密码</div>
          <div class="notice warning">${Icons.alert({ size: 14 })}<span class="nt-body"><span class="nt-title">首次登录请修改密码</span><span class="nt-desc">系统要求首次登录必须修改密码后再继续。</span></span></div>
          <button class="btn btn-block" id="lp-back">返回登录</button></div>`;
        document.getElementById("lp-back").onclick = restore;
        return;
      }
      UI.toast("登录成功", "success");
      location.hash = "/workbench";
    } catch (err) {
      /* 错误提示不得暴露账号是否存在（文档 5.1） */
      const text = err && err.message ? err.message : "登录失败，请稍后重试";
      const detail = (err && err.code === "INVALID_CREDENTIALS") ? '<span class="nt-desc">账号或密码错误、账号禁用、限速或服务暂不可用时均显示此提示。</span>' : "";
      host.innerHTML = `<div class="login-progress">
        <div class="lp-title" style="color:var(--danger-high);margin-bottom:12px">${Icons.alert({ size: 16 })} 登录未成功</div>
        <div class="notice error">${Icons.alert({ size: 14 })}<span class="nt-body"><span class="nt-title">${UI.esc(text)}</span>${detail}</span></div>
        <button class="btn btn-primary btn-block" id="lp-back">返回重新登录</button>
      </div>`;
      document.getElementById("lp-back").onclick = restore;
    }
  });

  function restore() {
    host.style.display = "none";
    host.innerHTML = "";
    wrap.style.display = "block";
    const acc = document.getElementById("account");
    if (acc) acc.focus();
  }
});

/* ---------------- 我的工作台 /workbench（文档 5.2） ---------------- */
App.register("workbench", (container) => {
  container.innerHTML = UI.topbar("我的工作台", "我的工作台", "") +
    `<div id="wb-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + "/me/workbench").then((wb) => {
    const card = (title, items, empty, actionLabel, actionHref) => {
      const rows = items.length ? items.map((it) => {
        const dl = UI.deadlineText(it.deadline);
        return `<tr class="row-link" ${actionHref ? `onclick="location.hash='${actionHref}'"` : ""}>
          <td>${UI.esc(it.project)}</td>
          <td>${UI.esc(it.type)}</td>
          <td>${riskBadge(it.risk)}</td>
          <td>${UI.esc(it.owner)}</td>
          <td class="${dl.cls} num">${dl.text}</td>
          <td>${statusBadge(it.state)}</td>
          <td>${actionLabel ? `<a class="btn btn-ghost btn-sm" href="${actionHref}">${UI.esc(actionLabel)} ${Icons.chevronRight({ size: 13 })}</a>` : "—"}</td>
        </tr>`;
      }).join("") : UI.emptyState(empty);
      return `<div class="card">
        <div class="card-head"><h2>${UI.esc(title)}</h2><span class="sub">${items.length} 项</span></div>
        <div class="table-wrap"><table class="grid">
          <thead><tr><th>项目</th><th>事项类型</th><th>风险等级</th><th>责任人</th><th>截止时间</th><th>当前状态</th><th>动作</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      </div>`;
    };

    const todoHref = "#/projects/p-2001/reviews";
    const html = `
      <div class="card-grid grid-4" style="margin-bottom:16px">
        <div class="stat"><div class="label">我的待办</div><div class="value num">${wb.todos.length}</div><div class="meta">需我处理</div></div>
        <div class="stat"><div class="label">待人工确认</div><div class="value num">${wb.pendingHuman.length}</div><div class="meta">关口待确认</div></div>
        <div class="stat"><div class="label">阻断事项</div><div class="value num" style="color:var(--danger-block)">${wb.blocking.length}</div><div class="meta">须解决/豁免</div></div>
        <div class="stat"><div class="label">运行中任务</div><div class="value num">${wb.runningTasks.length}</div><div class="meta">长任务轮询中</div></div>
      </div>
      ${card("我的待办", wb.todos, "暂无待办", "前往处理", todoHref)}
      ${card("待人工确认", wb.pendingHuman, "暂无待确认", "前往确认", "#/projects/p-2001/requirements")}
      ${card("阻断事项", wb.blocking, "无阻断事项", "查看", "#/projects/p-2001/reviews")}
      ${card("临近截止项目", wb.nearDeadline, "无临近截止", "进入项目", "#/projects/p-2001/overview")}

      <div class="card">
        <div class="card-head"><h2>运行中任务</h2><span class="sub">每 2~3 秒轮询</span></div>
        <div class="table-wrap"><table class="grid">
          <thead><tr><th>任务类型</th><th>当前阶段</th><th>进度</th><th>预计剩余步骤</th><th>更新时间</th><th>状态</th></tr></thead>
          <tbody>${wb.runningTasks.map((t) => `<tr>
            <td>${UI.esc(t.type)}</td><td>${UI.esc(t.stage)}</td>
            <td><div class="progress" style="width:120px"><span style="width:${t.progress}%"></span></div><span class="num text-xs">${t.progress}%</span></td>
            <td class="num">${t.remainingSteps}</td><td class="num">${UI.fmtDateTime(t.updatedAt)}</td>
            <td>${statusBadge(t.state)}</td></tr>`).join("") || UI.emptyState("无运行中任务")}</tbody>
        </table></div>
      </div>

      <div class="card">
        <div class="card-head"><h2>失败任务摘要</h2></div>
        <div class="table-wrap"><table class="grid">
          <thead><tr><th>任务类型</th><th>失败阶段</th><th>失败原因</th><th>更新时间</th><th>动作</th></tr></thead>
          <tbody>${wb.failedTasks.map((t) => `<tr>
            <td>${UI.esc(t.type)}</td><td>${UI.esc(t.stage)}</td>
            <td class="risk-high">${UI.esc(t.failedReason)}</td>
            <td class="num">${UI.fmtDateTime(t.updatedAt)}</td>
            <td><button class="btn btn-sm" onclick="UI.toast('已触发重试','info')">${Icons.retry({ size: 13 })} 重试</button> <button class="btn btn-sm" onclick="UI.toast('转人工处理','info')">${Icons.user({ size: 13 })} 人工处理</button></td>
          </tr>`).join("") || UI.emptyState("无失败任务")}</tbody>
        </table></div>
      </div>

      <div class="card">
        <div class="card-head"><h2>最近访问项目</h2></div>
        <div class="row wrap">
          ${wb.recentProjects.map((pid) => { const p = MockData.projects.find((x) => x.id === pid); return p ? `<a class="tag soft" href="#/projects/${p.id}/overview">${UI.esc(p.name)}</a>` : ""; }).join("")}
        </div>
      </div>`;
    document.getElementById("wb-content").innerHTML = html;
  }).catch((err) => { UI.handleError(err); });
});

/* ---------------- 项目列表 /projects（文档 5.3） ---------------- */
App.register("projects", (container) => {
  const session = ApiClient.getSession();
  const canCreate = UI.can(session.user.role, "create_project");
  container.innerHTML = UI.topbar("项目列表", "项目列表",
    canCreate ? `<a class="btn btn-primary" href="#/projects/new">${Icons.plus({ size: 14 })} 新建项目</a>` : "") +
    `<div id="proj-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + "/projects").then((data) => {
    const items = data.items;
    const methods = [...new Set(items.map((i) => i.procurementMethod))];
    const statuses = [...new Set(items.map((i) => i.status))];
    const html = `
      <div class="card">
        <div class="toolbar">
          <div class="search">${Icons.search({ size: 15 })}<input id="f-search" placeholder="搜索项目名称 / 外部编号" /></div>
          <select class="filter" id="f-method"><option value="">采购方式</option>${methods.map((m) => `<option>${UI.esc(m)}</option>`).join("")}</select>
          <select class="filter" id="f-status"><option value="">项目状态</option>${statuses.map((s) => `<option value="${s}">${UI.esc(statusMeta(s).label)}</option>`).join("")}</select>
          <select class="filter" id="f-owner"><option value="">负责人</option>${[...new Set(items.map((i) => i.ownerName))].map((o) => `<option>${UI.esc(o)}</option>`).join("")}</select>
          <span class="spacer"></span>
          <span class="text-sm secondary">共 ${items.length} 个项目 · 最近访问置顶</span>
        </div>
        <div class="table-wrap"><table class="grid">
          <thead><tr><th>项目名称</th><th>外部项目编号</th><th>采购方式</th><th>项目状态</th><th>当前阶段</th><th>阻断风险</th><th>待确认</th><th>截止时间</th><th>最后更新</th><th>操作</th></tr></thead>
          <tbody id="proj-rows"></tbody>
        </table></div>
      </div>`;
    document.getElementById("proj-content").innerHTML = html;

    const renderRows = (list) => {
      const tb = document.getElementById("proj-rows");
      if (!list.length) { tb.innerHTML = UI.emptyState("无匹配项目"); return; }
      tb.innerHTML = list.map((p) => {
        const dl = UI.deadlineText(p.deadline);
        return `<tr class="row-link" onclick="location.hash='#/projects/${p.id}/overview'">
          <td><strong>${UI.esc(p.name)}</strong><div class="text-xs muted">${UI.esc(p.packageName)}</div></td>
          <td class="num">${UI.esc(p.externalNo)}</td>
          <td>${UI.esc(p.procurementMethod)}</td>
          <td>${statusBadge(p.status)}</td>
          <td>${UI.esc(p.currentPhase)}</td>
          <td class="num ${p.blockRisks ? "risk-block" : ""}">${p.blockRisks}</td>
          <td class="num">${p.pendingConfirmations}</td>
          <td class="num ${dl.cls}">${dl.text}</td>
          <td class="num">${UI.fmtDateTime(p.lastUpdated)}</td>
          <td><a class="btn btn-sm" href="#/projects/${p.id}/overview">进入项目</a></td>
        </tr>`;
      }).join("");
    };
    renderRows(items);

    const applyFilter = () => {
      const q = document.getElementById("f-search").value.trim().toLowerCase();
      const m = document.getElementById("f-method").value;
      const s = document.getElementById("f-status").value;
      const o = document.getElementById("f-owner").value;
      const filtered = items.filter((p) =>
        (!q || p.name.toLowerCase().includes(q) || p.externalNo.toLowerCase().includes(q)) &&
        (!m || p.procurementMethod === m) &&
        (!s || p.status === s) &&
        (!o || p.ownerName === o));
      renderRows(filtered);
    };
    ["f-search", "f-method", "f-status", "f-owner"].forEach((id) => {
      document.getElementById(id).addEventListener("input", applyFilter);
      document.getElementById(id).addEventListener("change", applyFilter);
    });
  }).catch((err) => UI.handleError(err));
});

/* ---------------- 新建项目 /projects/new（文档 5.4，三步向导） ---------------- */
App.register("newProject", (container) => {
  let step = 1;
  const form = { members: [], files: [] };

  container.innerHTML = UI.topbar("新建项目", "新建项目", `<a class="btn btn-ghost" href="#/projects">取消</a>`) +
    `<div class="card" style="max-width:840px"><div id="np-stepper"></div><div id="np-body"></div></div>`;

  const steps = [
    { n: 1, t: "项目基本信息" },
    { n: 2, t: "项目成员" },
    { n: 3, t: "采购文件" },
  ];
  const renderStepper = () => {
    document.getElementById("np-stepper").innerHTML = `<div class="stepper">` + steps.map((s, i) => {
      const cls = s.n === step ? "active" : s.n < step ? "done" : "";
      return `<div class="step ${cls}"><span class="num">${s.n < step ? Icons.check({ size: 13 }) : s.n}</span><span class="txt">${UI.esc(s.t)}</span></div>` + (i < steps.length - 1 ? `<span class="line"></span>` : "");
    }).join("") + `</div>`;
  };

  const renderStep = () => {
    renderStepper();
    const body = document.getElementById("np-body");
    if (step === 1) {
      body.innerHTML = `<div class="form-grid">
        <div class="field"><label>项目名称<span class="req">*</span></label><input class="control" id="np-name" placeholder="例如：市政务云迁移与运维服务项目" /><span class="err" id="np-name-e"></span></div>
        <div class="field"><label>外部项目编号<span class="req">*</span></label><input class="control num" id="np-ext" placeholder="例如：GPCG-2026-0815" /><span class="err" id="np-ext-e"></span></div>
        <div class="field"><label>采购方式<span class="req">*</span></label><select class="control" id="np-method"><option>公开招标</option><option>竞争性磋商</option><option>邀请招标</option><option>竞争性谈判</option></select></div>
        <div class="field"><label>项目类型<span class="req">*</span></label><select class="control" id="np-type"><option>政府采购-信息化服务</option><option>政府采购-货物</option><option>政府采购-工程</option></select></div>
        <div class="field"><label>截止时间<span class="req">*</span></label><input class="control" id="np-deadline" type="datetime-local" /><span class="err" id="np-deadline-e"></span></div>
        <div class="field"><label>主要来源<span class="req">*</span></label><input class="control" id="np-source" placeholder="例如：政府采购网" /></div>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:18px">
        <button class="btn btn-primary" id="np-next">下一步 ${Icons.chevronRight({ size: 14 })}</button>
      </div>`;
      document.getElementById("np-next").onclick = () => {
        const name = document.getElementById("np-name").value.trim();
        const ext = document.getElementById("np-ext").value.trim();
        const deadline = document.getElementById("np-deadline").value;
        let ok = true;
        document.getElementById("np-name-e").textContent = ""; document.getElementById("np-ext-e").textContent = ""; document.getElementById("np-deadline-e").textContent = "";
        if (!name) { document.getElementById("np-name-e").textContent = "请输入项目名称"; ok = false; }
        if (!ext) { document.getElementById("np-ext-e").textContent = "请输入外部项目编号"; ok = false; }
        if (!deadline) { document.getElementById("np-deadline-e").textContent = "请选择截止时间"; ok = false; }
        if (ok) { form.basic = { name, ext, method: document.getElementById("np-method").value, type: document.getElementById("np-type").value, deadline, source: document.getElementById("np-source").value }; step = 2; renderStep(); }
      };
    } else if (step === 2) {
      const roleOpts = Object.entries(ROLES).map(([k, v]) => `<option value="${k}">${UI.esc(v)}</option>`).join("");
      body.innerHTML = `<div class="notice info">${Icons.info({ size: 14 })}<span class="nt-body"><span class="nt-title">项目成员</span><span class="nt-desc">指定角色、用户、职责，并标记是否为负责人。创建后将建立创建人项目成员关系。</span></span></div>
        <div id="np-members"></div>
        <button class="btn btn-sm" id="np-add-member">${Icons.plus({ size: 13 })} 添加成员</button>
        <div class="row" style="justify-content:space-between;margin-top:18px">
          <button class="btn" id="np-prev">上一步</button>
          <button class="btn btn-primary" id="np-next">下一步 ${Icons.chevronRight({ size: 14 })}</button>
        </div>`;
      const renderMembers = () => {
        document.getElementById("np-members").innerHTML = form.members.map((m, i) => `
          <div class="card" style="margin-bottom:8px;padding:12px 14px">
            <div class="row wrap">
              <select class="control" style="max-width:240px" data-i="${i}" data-k="role">${roleOpts.replace(`value="${m.role}"`, `value="${m.role}" selected`)}</select>
              <input class="control" style="max-width:200px" placeholder="用户账号" data-i="${i}" data-k="user" value="${UI.esc(m.user || "")}" />
              <input class="control" style="flex:1;min-width:200px" placeholder="职责说明" data-i="${i}" data-k="duty" value="${UI.esc(m.duty || "")}" />
              <label class="row" style="gap:4px;white-space:nowrap"><input type="checkbox" data-i="${i}" data-k="leader" ${m.leader ? "checked" : ""}/> 负责人</label>
              <button class="btn btn-sm btn-danger" data-del="${i}">${Icons.close({ size: 13 })}</button>
            </div>
          </div>`).join("");
        document.querySelectorAll("#np-members [data-i]").forEach((el) => {
          el.addEventListener("input", () => {
            const i = +el.dataset.i, k = el.dataset.k;
            form.members[i][k] = k === "leader" ? el.checked : el.value;
          });
        });
        document.querySelectorAll("#np-members [data-del]").forEach((b) => b.onclick = () => { form.members.splice(+b.dataset.del, 1); renderMembers(); });
      };
      renderMembers();
      document.getElementById("np-add-member").onclick = () => { form.members.push({ role: "AUTHOR", user: "", duty: "", leader: form.members.length === 0 }); renderMembers(); };
      document.getElementById("np-prev").onclick = () => { step = 1; renderStep(); };
      document.getElementById("np-next").onclick = () => {
        if (!form.members.some((m) => m.leader)) { UI.toast("请至少指定一名负责人", "warning"); return; }
        step = 3; renderStep();
      };
    } else {
      body.innerHTML = `<div class="notice info">${Icons.upload({ size: 14 })}<span class="nt-body"><span class="nt-title">采购文件</span><span class="nt-desc">上传文件、填写来源、文件分类，并选择是否作为初始有效版本。</span></span></div>
        <div class="field" style="margin-top:12px"><label>文件上传<span class="req">*</span></label>
          <div class="card" style="border-style:dashed;text-align:center;padding:24px;color:var(--text-tertiary)">
            ${Icons.upload({ size: 22 })}<div style="margin-top:6px">拖拽或点击选择采购文件（PDF / DOCX）</div>
            <input type="file" id="np-file" style="margin-top:8px" />
          </div>
        </div>
        <div class="form-grid" style="grid-template-columns:1fr 1fr;margin-top:12px">
          <div class="field"><label>来源</label><input class="control" id="np-fsource" placeholder="例如：政府采购网" /></div>
          <div class="field"><label>文件分类</label><select class="control" id="np-fcat"><option>采购文件</option><option>技术附件</option><option>澄清文件</option><option>补遗文件</option></select></div>
        </div>
        <label class="row" style="gap:6px;margin-top:10px"><input type="checkbox" id="np-initial" checked /> 作为初始有效版本</label>
        <div class="row" style="justify-content:space-between;margin-top:18px">
          <button class="btn" id="np-prev">上一步</button>
          <button class="btn btn-primary" id="np-submit">${Icons.check({ size: 14 })} 创建项目</button>
        </div>`;
      document.getElementById("np-prev").onclick = () => { step = 2; renderStep(); };
      document.getElementById("np-submit").onclick = async () => {
        const fileEl = document.getElementById("np-file");
        if (!fileEl.value) { UI.toast("请上传采购文件", "warning"); return; }
        const btn = document.getElementById("np-submit");
        btn.disabled = true; btn.textContent = "创建中…";
        try {
          /* 创建项目、主采购包、创建人项目成员关系与审计事件（文档 5.4） */
          await ApiClient.post(ApiClient.BASE + "/projects", { ...form }, { idempotencyKey: "idem-newproj-" + Date.now() });
          UI.toast("项目已创建（含主采购包与成员关系）", "success");
          location.hash = "#/projects";
        } catch (err) {
          btn.disabled = false; btn.innerHTML = `${Icons.check({ size: 14 })} 创建项目`;
          /* 创建失败时保留表单输入并展示字段级错误（文档 5.4） */
          if (err && err.code === "VERSION_CONFLICT") UI.toast("创建冲突，请刷新后重试", "error");
          else UI.handleError(err);
        }
      };
    }
  };
  renderStep();
});

/* ---------------- 项目总览 /projects/{id}/overview（文档 5.5） ---------------- */
window.Views.overview = (container, id) => {
  const detail = MockData.projectDetail[id];
  container.innerHTML = UI.topbar("项目总览", "项目总览",
    `<a class="btn btn-sm" href="#/projects/${id}/documents">${Icons.documents({ size: 14 })} 文件与解析</a>`) +
    `<div id="ov-content"><div class="card">加载中…</div></div>`;

  ApiClient.get(ApiClient.BASE + `/projects/${id}/overview`).then((ov) => {
    const ctx = detail.context;
    const dl = UI.deadlineText(ctx.deadline);
    const phaseSeg = ov.phases.map((p) => {
      const cls = p.state === "done" ? "done" : p.state === "active" ? "active" : p.state === "block" ? "block" : "";
      return `<div class="seg ${cls}" title="${UI.esc(p.key)}"></div>`;
    }).join("");

    /* 未完成原因解释（文档 5.5：不能只给完成百分比） */
    const incompleteReasons = [];
    ov.phases.forEach((p) => { if (p.state !== "done") incompleteReasons.push(p.key); });
    if (ov.currentAction.blockReason) incompleteReasons.push("阻断：" + ov.currentAction.blockReason);

    const html = `
      <div class="card">
        <div class="card-head"><h2>项目抬头</h2></div>
        <dl class="kv">
          <dt>项目名称</dt><dd>${UI.esc(ctx.name)}</dd>
          <dt>外部编号</dt><dd class="num">${UI.esc(ctx.externalNo)}</dd>
          <dt>采购方式</dt><dd>${UI.esc(ctx.procurementMethod)}</dd>
          <dt>采购包</dt><dd>${UI.esc(ctx.packageName)}</dd>
          <dt>截止时间</dt><dd class="num ${dl.cls}">${dl.text}</dd>
          <dt>负责人</dt><dd>${UI.esc(ctx.ownerName)}</dd>
          <dt>当前状态</dt><dd>${statusBadge(ctx.status || "IN_PROGRESS")}</dd>
          <dt>有效文件版本</dt><dd>${UI.esc(ctx.validFileVersion)}</dd>
          <dt>确认报价版本</dt><dd>${UI.esc(ctx.confirmedQuotationVersion)}</dd>
          <dt>交接状态</dt><dd>${UI.esc(ctx.handoverStatus)}</dd>
        </dl>
      </div>

      <div class="card">
        <div class="card-head"><h2>阶段进度</h2><span class="sub">接入 → 解析 → 要求确认 → 响应规划 → 编制 → 审核 → 交接</span></div>
        <div class="progress steps" style="margin-bottom:10px">${phaseSeg}</div>
        <div class="row wrap text-sm secondary">
          ${ov.phases.map((p) => `<span class="${p.state === "block" ? "risk-block" : p.state === "active" ? "risk-medium" : ""}">${p.state === "done" ? Icons.check({ size: 13 }) : p.state === "block" ? Icons.alert({ size: 13 }) : "•"} ${UI.esc(p.key)}</span>`).join("")}
        </div>
      </div>

      <div class="card">
        <div class="card-head"><h2>当前行动卡</h2></div>
        <div class="notice ${ov.currentAction.blockReason ? "error" : "info"}">
          ${Icons.gate({ size: 16 })}
          <span class="nt-body">
            <span class="nt-title">下一步：${UI.esc(ov.currentAction.next)}</span>
            <span class="nt-desc">责任角色：${UI.esc(ov.currentAction.role)}</span>
            ${ov.currentAction.blockReason ? `<span class="nt-desc">阻断原因：${UI.esc(ov.currentAction.blockReason)}</span>` : ""}
          </span>
          <a class="btn btn-primary btn-sm" href="#/projects/${id}/${ov.currentAction.button.includes("审核") ? "reviews" : "requirements"}">${UI.esc(ov.currentAction.button)} ${Icons.chevronRight({ size: 13 })}</a>
        </div>
        <div class="notice warning">${Icons.info({ size: 14 })}<span class="nt-body"><span class="nt-title">未完成原因</span><span class="nt-desc">尚未完成的阶段/事项：${UI.esc(incompleteReasons.join("、"))}</span></span></div>
      </div>

      <div class="card">
        <div class="card-head"><h2>待确认事项</h2><span class="sub">按风险、截止时间、影响范围排序</span></div>
        <div class="table-wrap"><table class="grid">
          <thead><tr><th>事项</th><th>风险等级</th><th>截止时间</th><th>影响范围</th></tr></thead>
          <tbody>${ov.pending.map((p) => { const dl = UI.deadlineText(p.deadline); return `<tr><td>${UI.esc(p.type)}</td><td>${riskBadge(p.risk)}</td><td class="num ${dl.cls}">${dl.text}</td><td>${UI.esc(p.impact)}</td></tr>`; }).join("") || UI.emptyState("无待确认事项")}</tbody>
        </table></div>
      </div>

      <div class="card">
        <div class="card-head"><h2>运行任务</h2></div>
        <div class="table-wrap"><table class="grid">
          <thead><tr><th>任务类型</th><th>当前阶段</th><th>进度</th><th>预计剩余步骤</th><th>失败原因</th><th>动作</th></tr></thead>
          <tbody>${ov.runningTasks.map((t) => `<tr>
            <td>${UI.esc(t.type)}</td><td>${UI.esc(t.stage)}</td>
            <td><div class="progress" style="width:120px"><span style="width:${t.progress}%"></span></div><span class="num text-xs">${t.progress}%</span></td>
            <td class="num">${t.remainingSteps}</td>
            <td class="${t.failedReason ? "risk-high" : ""}">${UI.esc(t.failedReason || "—")}</td>
            <td>${t.state === "FAILED" ? `<button class="btn btn-sm" onclick="UI.toast('已触发重试','info')">${Icons.retry({ size: 13 })} 重试</button>` : `<button class="btn btn-sm" onclick="UI.toast('转人工接管','info')">${Icons.user({ size: 13 })} 人工接管</button>`}</td>
          </tr>`).join("") || UI.emptyState("无运行任务")}</tbody>
        </table></div>
      </div>

      <div class="card">
        <div class="card-head"><h2>项目动态</h2><span class="sub">版本变化 / 人工确认 / 退回 / 审核 / 交接 / 递交</span></div>
        <ul class="timeline">
          ${ov.activities.map((a) => `<li class="${a.kind === "warn" ? "warn" : a.kind === "block" ? "block" : ""}">
            <div class="tl-time num">${UI.fmtDateTime(a.time)}</div>
            <div class="tl-title">${UI.esc(a.title)}</div>
            <div class="tl-desc">${UI.esc(a.desc)}</div>
          </li>`).join("")}
        </ul>
      </div>`;
    document.getElementById("ov-content").innerHTML = html;
  }).catch((err) => UI.handleError(err));
};

/* ---------------- 项目内分发 ---------------- */
App.register("project", (container, params) => {
  const fn = window.Views && window.Views[params.key];
  if (fn) fn(container, params.id);
  else container.innerHTML = UI.notice("warning", "子页面未实现", "未找到 " + params.key + " 视图");
});

window.Views = window.Views || {};
