/* 共享 UI 辅助：导航、模态框、抽屉、Toast、格式化、转义、权限判断 */
const UI = (() => {

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function fmtDateTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }

  /* 距离截止的剩余/逾期文案（状态不能用单一颜色表达，附文字） */
  function deadlineText(iso) {
    if (!iso) return { text: "—", cls: "" };
    const diff = new Date(iso).getTime() - Date.now();
    const day = 24 * 3600 * 1000;
    if (diff < 0) return { text: "已逾期 " + fmtDateTime(iso), cls: "risk-block" };
    if (diff < 3 * day) return { text: "临近 " + fmtDateTime(iso), cls: "risk-high" };
    return { text: fmtDateTime(iso), cls: "" };
  }

  /* 全局侧边导航 */
  const NAV = [
    { route: "/workbench", icon: "dashboard", label: "我的工作台" },
    { route: "/projects", icon: "projects", label: "项目列表" },
    { route: "/knowledge", icon: "knowledge", label: "企业资料库" },
    { route: "/templates-rules", icon: "templates", label: "模板与规则" },
    { route: "/admin", icon: "admin", label: "系统管理" },
  ];

  function renderSidebar(activeRoute) {
    const session = ApiClient.getSession();
    const items = NAV.map((n) => {
      const active = activeRoute === n.route || (n.route === "/projects" && activeRoute.startsWith("/projects"));
      return `<a class="nav-item ${active ? "active" : ""}" href="#${n.route}">
        <span class="ic">${Icons[n.icon]({ size: 16 })}</span>
        <span class="label">${n.label}</span>
      </a>`;
    }).join("");
    const roleLabel = session.user ? session.user.roleLabel : "";
    const name = session.user ? session.user.name : "";
    return `
      <aside class="sidebar">
        <div class="brand">
          <span class="logo">${Icons.gate({ size: 18 })}</span>
          <span>
            <span class="title">投标文件智能编制<br>与合规审核平台</span>
          </span>
        </div>
        <div class="nav-section">${items}</div>
        <div class="sidebar-footer">
          <span class="avatar">${esc(name.slice(0, 1))}</span>
          <span class="who">
            <span class="name">${esc(name)}</span><br>
            <span class="role">${esc(roleLabel)}</span>
          </span>
          <a class="btn btn-ghost btn-sm" href="#/login" title="退出登录" style="margin-left:auto" onclick="App.logout()">${Icons.logout({ size: 15 })}</a>
        </div>
      </aside>`;
  }

  /* 项目内二级导航 */
  const PROJECT_NAV = [
    { key: "overview", icon: "overview", label: "项目总览" },
    { key: "documents", icon: "documents", label: "文件与解析" },
    { key: "requirements", icon: "requirements", label: "要求与评分" },
    { key: "response-plan", icon: "plan", label: "响应规划" },
    { key: "authoring", icon: "authoring", label: "标书编制" },
    { key: "reviews", icon: "reviews", label: "审核与风险" },
    { key: "handover", icon: "handover", label: "交接与递交" },
    { key: "records", icon: "records", label: "项目记录" },
  ];

  function renderProjectBar(ctx, activeKey) {
    const items = PROJECT_NAV.map((n) => {
      const active = activeKey === n.key;
      return `<a class="${active ? "active" : ""}" href="#/projects/${ctx.id}/${n.key}">
        ${Icons[n.icon]({ size: 14 })} ${n.label}
      </a>`;
    }).join("");
    const dl = deadlineText(ctx.deadline);
    return `
      <div class="project-bar">
        <div class="ctx">
          <div class="pname">${esc(ctx.name)}</div>
          <div class="pmeta">${esc(ctx.externalNo)} · ${esc(ctx.packageName)} · 截止 <span class="${dl.cls}">${dl.text}</span> · 有效文件版本 ${esc(ctx.validFileVersion)} · 确认报价 ${esc(ctx.confirmedQuotationVersion)} · 阻断风险 ${ctx.blockRisks} · 交接 ${esc(ctx.handoverStatus)}</div>
        </div>
        <div class="subnav">${items}</div>
      </div>`;
  }

  /* 顶部条 */
  function topbar(crumb, title, actionsHtml) {
    return `<div class="topbar">
      <div>
        <div class="crumb">${esc(crumb)}</div>
        <h1>${esc(title)}</h1>
      </div>
      <div class="actions">${actionsHtml || ""}</div>
    </div>`;
  }

  /* 模态框 / 抽屉 / Toast */
  function modal({ title, body, footer, onClose }) {
    const host = document.getElementById("modal-host");
    host.innerHTML = `
      <div class="modal-mask open" id="modal-mask">
        <div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}">
          <div class="modal-head"><h2>${esc(title)}</h2><button class="btn btn-ghost btn-sm" aria-label="关闭">${Icons.close({ size: 16 })}</button></div>
          <div class="modal-body">${body}</div>
          <div class="modal-foot">${footer || ""}</div>
        </div>
      </div>`;
    const mask = document.getElementById("modal-mask");
    mask.querySelector(".modal-head button").onclick = closeModal;
    mask.addEventListener("click", (e) => { if (e.target === mask) closeModal(); });
    return { close: closeModal };
  }
  function closeModal() {
    const host = document.getElementById("modal-host");
    if (host) host.innerHTML = "";
  }

  function drawer({ title, body, footer, onClose }) {
    const host = document.getElementById("drawer-host");
    host.innerHTML = `
      <div class="drawer-mask open" id="drawer-mask">
        <div class="drawer" role="dialog" aria-modal="true" aria-label="${esc(title)}">
          <div class="drawer-head"><h2>${esc(title)}</h2><button class="btn btn-ghost btn-sm" aria-label="关闭">${Icons.close({ size: 16 })}</button></div>
          <div class="drawer-body">${body}</div>
          <div class="drawer-foot">${footer || ""}</div>
        </div>
      </div>`;
    const mask = document.getElementById("drawer-mask");
    mask.querySelector(".drawer-head button").onclick = closeDrawer;
    mask.addEventListener("click", (e) => { if (e.target === mask) closeDrawer(); });
    return { close: closeDrawer };
  }
  function closeDrawer() {
    const host = document.getElementById("drawer-host");
    if (host) host.innerHTML = "";
  }

  let toastTimer = [];
  function toast(msg, type = "info") {
    const host = document.getElementById("toast-host");
    const el = document.createElement("div");
    el.className = "toast " + type;
    el.textContent = msg;
    host.appendChild(el);
    setTimeout(() => { el.remove(); }, 3200);
  }

  function notice(kind, title, desc) {
    const ico = kind === "error" ? Icons.alert({ size: 16 }) : kind === "warning" ? Icons.alert({ size: 16 }) : kind === "success" ? Icons.check({ size: 16 }) : Icons.info({ size: 16 });
    return `<div class="notice ${kind}"><span class="ic">${ico}</span><span class="nt-body"><span class="nt-title">${esc(title)}</span>${desc ? `<span class="nt-desc">${esc(desc)}</span>` : ""}</span></div>`;
  }

  /* 错误码映射到用户提示（文档 7.4） */
  function handleError(err) {
    if (!err) return;
    switch (err.code) {
      case "UNAUTHENTICATED": App.redirectLogin(); break;
      case "FORBIDDEN": toast("无权限执行该操作", "error"); break;
      case "INVALID_STATE_TRANSITION": toast("当前状态不允许该操作，已刷新上下文", "warning"); break;
      case "VERSION_CONFLICT": toast("当前内容已更新，请重新加载", "warning"); break;
      case "GATE_NOT_READY": toast("人工关口未就绪，请先处理前置事项", "warning"); break;
      case "PARSE_FAILED": toast("解析失败：" + (err.message || ""), "error"); break;
      case "TASK_NOT_FOUND": toast("任务不存在，已停止轮询", "warning"); break;
      case "IDEMPOTENCY_CONFLICT": toast("已有相同请求正在处理", "warning"); break;
      default: toast(err.message || "操作失败", "error");
    }
  }

  /* 权限：仅控制前端显隐，最终权限由后端校验（文档 3 节） */
  function can(role, action) {
    const matrix = {
      BID_MANAGER: ["create_project", "assign_member", "confirm_gate", "submit_review", "confirm_handover", "confirm_quotation"],
      AUTHOR: ["edit_section", "handle_todo", "submit_review"],
      TECH: ["edit_tech_section", "confirm_tech_evidence"],
      COMMERCIAL: ["view_quotation", "select_plan", "confirm_quotation_ref"],
      DATA_ADMIN: ["upload_material", "maintain_version", "confirm_validity"],
      COMMERCIAL_REVIEWER: ["raise_issue", "return_fix", "review_close"],
      COMPLIANCE: ["raise_block_issue", "approve_exemption", "confirm_or_return"],
      SUBMITTER: ["confirm_receive", "register_submission", "upload_receipt"],
      SYS_ADMIN: ["manage_config", "manage_account", "view_audit", "view_runtime"],
    };
    const allowed = matrix[role] || [];
    return allowed.includes(action);
  }

  function emptyState(text) {
    return `<div class="empty-row"><td colspan="99">${esc(text)}</td></div>`;
  }

  return { esc, fmtDateTime, fmtDate, deadlineText, renderSidebar, renderProjectBar, topbar, modal, closeModal, drawer, closeDrawer, toast, notice, handleError, can, emptyState };
})();

window.UI = UI;
