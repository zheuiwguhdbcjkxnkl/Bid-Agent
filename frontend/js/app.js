/* 前端路由与启动（Hash Router，无需后端）
   文档 4.2 路由：/workbench、/projects、/projects/new、/projects/{id}/{key} 等
   文档 3 节：登录后进入“我的工作台”，不直接跳到最近项目。 */

const App = (() => {
  const views = {}; // 由各视图文件注册：views[name] = fn(container, params)
  function register(name, fn) { views[name] = fn; }

  function redirectLogin() {
    location.hash = "/login";
  }

  function parseHash() {
    let h = location.hash.replace(/^#/, "");
    if (!h || h === "/") h = "/workbench";
    return h;
  }

  function render() {
    const hash = parseHash();
    const session = ApiClient.getSession();

    /* 登录页：已登录则跳转工作台（文档 5.1） */
    if (hash === "/login") {
      if (session.loggedIn) { location.hash = "/workbench"; return; }
      const root = document.getElementById("app");
      root.innerHTML = `<div id="login-root"></div>`;
      if (views.login) views.login(document.getElementById("login-root"));
      else root.innerHTML = "<div class='content'>加载中…</div>";
      return;
    }

    /* 其余页面需登录 */
    if (!session.loggedIn) { redirectLogin(); return; }

    const root = document.getElementById("app");
    let html = `<div class="app-shell">${UI.renderSidebar(hash)}<div class="main">`;

    /* 项目内页面：解析 /projects/{id}/{key} */
    const projMatch = hash.match(/^\/projects\/([^/]+)\/([^/]+)$/);
    const newMatch = hash.match(/^\/projects\/new$/);
    const projListMatch = hash.match(/^\/projects$/);

    if (projMatch) {
      const id = projMatch[1];
      const key = projMatch[2];
      const detail = MockData.projectDetail[id];
      if (!detail) {
        html += `</div></div><div id="view-content"></div>`;
        root.innerHTML = html;
        document.getElementById("view-content").innerHTML = UI.notice("error", "项目不存在", "未找到项目 " + id);
        return;
      }
      html += UI.renderProjectBar(detail.context, key);
      html += `<div id="view-content" class="content"></div></div></div>`;
      root.innerHTML = html;
      if (views.project) views.project(document.getElementById("view-content"), { id, key });
      else document.getElementById("view-content").innerHTML = "视图未加载";
      return;
    }

    html += `<div id="view-content" class="content"></div></div></div>`;
    root.innerHTML = html;
    const content = document.getElementById("view-content");

    if (newMatch) { if (views.newProject) views.newProject(content); else content.innerHTML = "视图未加载"; return; }
    if (projListMatch) { if (views.projects) views.projects(content); else content.innerHTML = "视图未加载"; return; }

    /* 顶层路由 */
    const map = {
      "/workbench": "workbench",
      "/knowledge": "knowledge",
      "/templates-rules": "templatesRules",
      "/admin": "admin",
    };
    const name = map[hash];
    if (name && views[name]) { views[name](content); }
    else { content.innerHTML = UI.notice("warning", "页面未实现", "路由 " + hash + " 暂无视图"); }
  }

  function logout() {
    ApiClient.logout();
    UI.toast("已退出登录", "info");
    location.hash = "/login";
  }

  function start() {
    window.addEventListener("hashchange", render);
    render();
  }

  return { register, render, redirectLogin, logout, start, parseHash };
})();

window.App = App;
