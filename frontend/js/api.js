/* Mock API 客户端
   文档 8.1 统一约定：基础路径 /api/v1、Session Cookie 认证、长任务 202 + task_run_id、
   写请求携带 Idempotency-Key 与当前对象版本、成功直接返回契约对象。
   文档 7.3：V1 不使用 WebSocket/SSE，前端每 2~3 秒轮询任务。 */

const ApiClient = (() => {
  const BASE = "/api/v1";

  /* 模拟 Session（不持久化 JWT，符合 3 节权限规则） */
  const session = {
    loggedIn: false,
    user: null,
  };

  function getSession() { return session; }

  function login(account, password) {
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        if (account === "demo" && password === "demo123") {
          session.loggedIn = true;
          session.user = MockData.currentUser;
          resolve({ user: MockData.currentUser, mustChangePassword: false });
        } else if (account === "demo" && password !== "demo123") {
          reject({ code: "INVALID_CREDENTIALS", message: "账号或密码错误，请重试", request_id: "r-001", details: {} });
        } else {
          /* 错误提示不得暴露账号是否存在（文档 5.1） */
          reject({ code: "INVALID_CREDENTIALS", message: "账号或密码错误，请重试", request_id: "r-002", details: {} });
        }
      }, 500);
    });
  }

  function logout() {
    session.loggedIn = false;
    session.user = null;
  }

  function requireAuth() {
    if (!session.loggedIn) {
      const err = { code: "UNAUTHENTICATED", message: "会话已过期或未登录", request_id: "r-auth", details: {} };
      return { ok: false, error: err };
    }
    return { ok: true };
  }

  /* 统一错误结构（文档 7.4） */
  function makeError(code, message, details = {}) {
    return { code, message, request_id: "r-" + Math.random().toString(36).slice(2, 8), details };
  }

  /* 模拟 GET：根据路径返回 Mock 数据 */
  function get(path) {
    return new Promise((resolve, reject) => {
      const auth = requireAuth();
      if (!auth.ok) return reject(auth.error);
      setTimeout(() => {
        if (path === BASE + "/me/workbench") return resolve(MockData.workbench);
        if (path === BASE + "/projects") return resolve({ items: MockData.projects, page: 1, page_size: 20, total: MockData.projects.length });
        const pm = path.match(new RegExp("^" + BASE + "/projects/([^/]+)/overview$"));
        if (pm) {
          const d = MockData.projectDetail[pm[1]];
          if (!d) return reject(makeError("NOT_FOUND", "项目不存在"));
          return resolve(d.overview);
        }
        const pctx = path.match(new RegExp("^" + BASE + "/projects/([^/]+)/context$"));
        if (pctx) {
          const d = MockData.projectDetail[pctx[1]];
          if (!d) return reject(makeError("NOT_FOUND", "项目不存在"));
          return resolve(d.context);
        }
        const pdocs = path.match(new RegExp("^" + BASE + "/projects/([^/]+)/documents$"));
        if (pdocs) {
          const d = MockData.projectDetail[pdocs[1]];
          if (!d) return reject(makeError("NOT_FOUND", "项目不存在"));
          return resolve(d.documents);
        }
        const preq = path.match(new RegExp("^" + BASE + "/projects/([^/]+)/requirements$"));
        if (preq) {
          const d = MockData.projectDetail[preq[1]];
          if (!d) return reject(makeError("NOT_FOUND", "项目不存在"));
          return resolve(d.requirements);
        }
        const pplan = path.match(new RegExp("^" + BASE + "/projects/([^/]+)/response-plan$"));
        if (pplan) {
          const d = MockData.projectDetail[pplan[1]];
          if (!d) return reject(makeError("NOT_FOUND", "项目不存在"));
          return resolve(d.responsePlan);
        }
        const psec = path.match(new RegExp("^" + BASE + "/projects/([^/]+)/sections$"));
        if (psec) {
          const d = MockData.projectDetail[psec[1]];
          if (!d) return reject(makeError("NOT_FOUND", "项目不存在"));
          return resolve(d.authoring.sections);
        }
        const prev = path.match(new RegExp("^" + BASE + "/projects/([^/]+)/reviews$"));
        if (prev) {
          const d = MockData.projectDetail[prev[1]];
          if (!d) return reject(makeError("NOT_FOUND", "项目不存在"));
          return resolve(d.reviews);
        }
        const phand = path.match(new RegExp("^" + BASE + "/projects/([^/]+)/handover-packages$"));
        if (phand) {
          const d = MockData.projectDetail[phand[1]];
          if (!d) return reject(makeError("NOT_FOUND", "项目不存在"));
          return resolve(d.handover);
        }
        const ptl = path.match(new RegExp("^" + BASE + "/projects/([^/]+)/timeline$"));
        if (ptl) {
          const d = MockData.projectDetail[ptl[1]];
          if (!d) return reject(makeError("NOT_FOUND", "项目不存在"));
          return resolve(d.records.events);
        }
        const paud = path.match(new RegExp("^" + BASE + "/projects/([^/]+)/audit-events$"));
        if (paud) {
          const d = MockData.projectDetail[paud[1]];
          if (!d) return reject(makeError("NOT_FOUND", "项目不存在"));
          return resolve(d.records.events);
        }
        if (path === BASE + "/knowledge" || path.endsWith("/knowledge")) return resolve(MockData.knowledge);
        if (path === BASE + "/templates-rules") return resolve(MockData.templatesRules);
        if (path === BASE + "/admin/users") return resolve(MockData.admin);
        reject(makeError("NOT_FOUND", "接口未实现（Mock）: " + path));
      }, 200);
    });
  }

  /* 模拟长任务创建：返回 202 + task_run_id */
  function createTask(type) {
    return new Promise((resolve) => {
      const auth = requireAuth();
      if (!auth.ok) return;
      setTimeout(() => {
        resolve({ task_run_id: "t-" + Math.floor(Math.random() * 9000 + 1000), type, accepted: true });
      }, 200);
    });
  }

  /* 模拟任务轮询（文档 7.3）：QUEUED→RUNNING→SUCCEEDED / FAILED / WAITING_HUMAN / CANCELLED */
  function pollTask(taskRunId) {
    return new Promise((resolve) => {
      setTimeout(() => {
        if (taskRunId === "t-880") {
          return resolve({ task_run_id: taskRunId, type: "采购文件解析", state: "FAILED", stage: "OCR 识别", progress: 40, failedReason: "第 58 页图像旋转异常，无法稳定切分", startedAt: "2026-08-20T14:10", updatedAt: "2026-08-20T14:22" });
        }
        if (taskRunId === "t-901") {
          return resolve({ task_run_id: taskRunId, type: "多 Agent 全审核链路", state: "RUNNING", stage: "一致性检查", progress: 72, remainingSteps: 3, startedAt: "2026-08-20T15:40", updatedAt: "2026-08-20T16:20" });
        }
        return resolve({ task_run_id: taskRunId, type: "异步任务", state: "SUCCEEDED", stage: "完成", progress: 100, startedAt: "2026-08-20T16:00", updatedAt: "2026-08-20T16:05" });
      }, 300);
    });
  }

  /* 模拟写操作（携带 Idempotency-Key 与版本号） */
  function post(path, body, opts = {}) {
    return new Promise((resolve, reject) => {
      const auth = requireAuth();
      if (!auth.ok) return reject(auth.error);
      const idem = opts.idempotencyKey || ("idem-" + Math.random().toString(36).slice(2, 10));
      const version = opts.version;
      setTimeout(() => {
        /* 演示用：版本冲突示例 */
        if (opts.simulateConflict) {
          return reject(makeError("VERSION_CONFLICT", "当前版本已变化，请刷新后重试", { current_version: (version || 1) + 1 }));
        }
        resolve({ ok: true, idempotency_key: idem, version: version || 1, request_id: "r-" + Math.random().toString(36).slice(2, 8) });
      }, 300);
    });
  }

  return { BASE, getSession, login, logout, get, createTask, pollTask, post, makeError, requireAuth };
})();

window.ApiClient = ApiClient;
