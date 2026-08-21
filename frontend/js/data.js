/* Mock 数据 —— 结构与真实 API 响应保持一致（文档 8.1：Mock API 与真实 API 使用相同响应结构）。
   仅用于前端原型演示，字段名遵循交付文档第 8 节 API 清单与第 10/11 节展示边界。 */

const ROLES = {
  BID_MANAGER: "投标经理/项目负责人",
  AUTHOR: "标书编写人",
  TECH: "技术方案人员",
  COMMERCIAL: "商务/报价人员",
  DATA_ADMIN: "资料管理员",
  COMMERCIAL_REVIEWER: "商务审核人员",
  COMPLIANCE: "合规/法务人员",
  SUBMITTER: "投标递交责任人",
  SYS_ADMIN: "系统管理员",
};

const RISK_LEVELS = {
  INFO: { key: "INFO", label: "提示", cls: "risk-info" },
  MEDIUM: { key: "MEDIUM", label: "中风险", cls: "risk-medium" },
  HIGH: { key: "HIGH", label: "高风险", cls: "risk-high" },
  BLOCK: { key: "BLOCK", label: "阻断", cls: "risk-block" },
};

/* 文档 7.1 状态枚举 */
const STATUS_LABELS = {
  PREPARING: "准备中",
  ANALYZING: "分析中",
  WAITING_HUMAN: "待人工",
  ISSUES_FOUND: "存在问题",
  IN_PROGRESS: "编制中",
  UNDER_REVIEW: "审核中",
  READY_FOR_HANDOVER: "待交接",
  HANDED_OVER: "已交接",
  SUBMITTED: "已登记人工递交",
  STALE: "已失效",
  PARSE_FAILED: "解析失败",
  EXPIRED: "已过期",
};

/* 文档 7.1：未知枚举安全降级 */
function statusMeta(code) {
  if (STATUS_LABELS[code]) return { code, label: STATUS_LABELS[code], known: true };
  return { code, label: "未知状态(" + code + ")", known: false };
}
function statusBadge(code) {
  const s = statusMeta(code);
  if (!s.known) return `<span class="badge neutral"><span class="dot solid"></span>${s.label}</span>`;
  const map = {
    PREPARING: "neutral", ANALYZING: "info", WAITING_HUMAN: "warning",
    ISSUES_FOUND: "danger-high", IN_PROGRESS: "primary", UNDER_REVIEW: "primary",
    READY_FOR_HANDOVER: "primary", HANDED_OVER: "success", SUBMITTED: "success",
    STALE: "stale", PARSE_FAILED: "danger-high", EXPIRED: "danger-block",
  };
  const variant = map[code] || "neutral";
  return `<span class="badge ${variant}"><span class="dot solid"></span>${s.label}</span>`;
}
function riskBadge(key) {
  const r = RISK_LEVELS[key] || { label: key, cls: "risk-info" };
  const variant = key === "HIGH" ? "danger-high" : key === "BLOCK" ? "danger-block" : key === "MEDIUM" ? "warning" : "neutral";
  const ico = (key === "HIGH" || key === "BLOCK") ? Icons.alert({ size: 13 }) : Icons.info({ size: 13 });
  return `<span class="badge ${variant}">${ico}${r.label}</span>`;
}

const MockData = {
  currentUser: {
    id: "u-1001",
    name: "赵明",
    role: "BID_MANAGER",
    roleLabel: ROLES.BID_MANAGER,
    account: "zhaoming",
    mustChangePassword: false,
  },

  /* GET /api/v1/projects */
  projects: [
    {
      id: "p-2001",
      name: "市政务云迁移与运维服务项目",
      externalNo: "GPCG-2026-0815",
      procurementMethod: "公开招标",
      projectType: "政府采购-信息化服务",
      status: "UNDER_REVIEW",
      deadline: "2026-09-15T17:00:00+08:00",
      ownerName: "赵明",
      currentPhase: "审核与风险",
      blockRisks: 1,
      pendingConfirmations: 2,
      lastUpdated: "2026-08-20T16:30:00+08:00",
      packageName: "采购包A：政务云迁移",
      validFileVersion: "v3（含补遗）",
      confirmedQuotationVersion: "报价方案 v2",
      handoverStatus: "未建立",
      source: "政府采购网",
    },
    {
      id: "p-2002",
      name: "区教育一体化平台建设项目",
      externalNo: "GPCG-2026-0722",
      procurementMethod: "竞争性磋商",
      projectType: "政府采购-信息化服务",
      status: "IN_PROGRESS",
      deadline: "2026-09-02T10:00:00+08:00",
      ownerName: "李红",
      currentPhase: "标书编制",
      blockRisks: 0,
      pendingConfirmations: 1,
      lastUpdated: "2026-08-19T09:10:00+08:00",
      packageName: "采购包A：一体化平台",
      validFileVersion: "v1",
      confirmedQuotationVersion: "—",
      handoverStatus: "未建立",
      source: "采购人自建平台",
    },
    {
      id: "p-2003",
      name: "市交通数据治理与共享平台",
      externalNo: "GPCG-2026-0630",
      procurementMethod: "公开招标",
      projectType: "政府采购-信息化服务",
      status: "READY_FOR_HANDOVER",
      deadline: "2026-08-28T15:00:00+08:00",
      ownerName: "王强",
      currentPhase: "交接与递交",
      blockRisks: 0,
      pendingConfirmations: 0,
      lastUpdated: "2026-08-18T14:00:00+08:00",
      packageName: "采购包A：数据治理",
      validFileVersion: "v2",
      confirmedQuotationVersion: "报价方案 v1",
      handoverStatus: "基线已建立·待接收",
      source: "政府采购网",
    },
  ],

  /* GET /api/v1/me/workbench */
  workbench: {
    todos: [
      { projectId: "p-2001", project: "市政务云迁移与运维服务项目", type: "审核问题待处理", risk: "BLOCK", owner: "赵明", deadline: "2026-08-21T18:00:00+08:00", state: "UNDER_REVIEW", detail: "review-issues/ri-3301" },
      { projectId: "p-2002", project: "区教育一体化平台建设项目", type: "章节初稿待提交审核", risk: "INFO", owner: "李红", deadline: "2026-08-23T18:00:00+08:00", state: "IN_PROGRESS", detail: "sections/s-2210" },
      { projectId: "p-2001", project: "市政务云迁移与运维服务项目", type: "要求基线确认待办", risk: "HIGH", owner: "赵明", deadline: "2026-08-22T12:00:00+08:00", state: "WAITING_HUMAN", detail: "requirements" },
    ],
    pendingHuman: [
      { projectId: "p-2001", project: "市政务云迁移与运维服务项目", type: "响应规划确认", risk: "HIGH", owner: "赵明", deadline: "2026-08-22T12:00:00+08:00", state: "WAITING_HUMAN" },
      { projectId: "p-2003", project: "市交通数据治理与共享平台", type: "审核结果确认", risk: "INFO", owner: "王强", deadline: "2026-08-25T12:00:00+08:00", state: "WAITING_HUMAN" },
    ],
    blocking: [
      { projectId: "p-2001", project: "市政务云迁移与运维服务项目", type: "资质有效期不足", risk: "BLOCK", owner: "资料管理员", deadline: "2026-08-21T18:00:00+08:00", state: "ISSUES_FOUND", detail: "review-issues/ri-3301" },
    ],
    nearDeadline: [
      { projectId: "p-2003", project: "市交通数据治理与共享平台", type: "人工外部递交截止", risk: "MEDIUM", owner: "王强", deadline: "2026-08-28T15:00:00+08:00", state: "READY_FOR_HANDOVER" },
      { projectId: "p-2002", project: "区教育一体化平台建设项目", type: "编制完成截止", risk: "MEDIUM", owner: "李红", deadline: "2026-09-02T10:00:00+08:00", state: "IN_PROGRESS" },
    ],
    runningTasks: [
      { taskRunId: "t-901", type: "多 Agent 全审核链路", stage: "一致性检查", progress: 72, remainingSteps: 3, startedAt: "2026-08-20T15:40:00+08:00", updatedAt: "2026-08-20T16:20:00+08:00", state: "RUNNING" },
    ],
    failedTasks: [
      { taskRunId: "t-880", type: "采购文件解析", stage: "OCR 识别", progress: 40, failedReason: "第 58 页图像旋转异常，无法稳定切分", startedAt: "2026-08-20T14:10:00+08:00", updatedAt: "2026-08-20T14:22:00+08:00", state: "FAILED" },
    ],
    recentProjects: ["p-2001", "p-2003", "p-2002"],
  },

  /* 项目内详情：仅 p-2001 完整填充，其余复用基础项目对象 */
  projectDetail: {
    "p-2001": {
      context: {
        name: "市政务云迁移与运维服务项目",
        externalNo: "GPCG-2026-0815",
        procurementMethod: "公开招标",
        packageName: "采购包A：政务云迁移",
        deadline: "2026-09-15T17:00:00+08:00",
        ownerName: "赵明",
        status: "UNDER_REVIEW",
        validFileVersion: "v3（含补遗）",
        confirmedQuotationVersion: "报价方案 v2",
        blockRisks: 1,
        handoverStatus: "未建立",
        currentPhase: "审核与风险",
      },
      overview: {
        phases: [
          { key: "接入", state: "done" },
          { key: "解析", state: "done" },
          { key: "要求确认", state: "active" },
          { key: "响应规划", state: "done" },
          { key: "编制", state: "done" },
          { key: "审核", state: "active" },
          { key: "交接", state: "block" },
        ],
        currentAction: {
          next: "确认要求基线并复核阻断风险",
          role: "投标经理/项目负责人",
          blockReason: "存在 1 项阻断风险（资质有效期）未解决或未经授权豁免",
          button: "前往审核与风险",
        },
        pending: [
          { id: "pend-1", type: "要求基线确认", risk: "HIGH", deadline: "2026-08-22T12:00:00+08:00", impact: "影响章节生成与报价引用" },
          { id: "pend-2", type: "响应规划确认", risk: "HIGH", deadline: "2026-08-22T12:00:00+08:00", impact: "影响正式章节生成" },
        ],
        runningTasks: [
          { taskRunId: "t-901", type: "多 Agent 全审核链路", stage: "一致性检查", progress: 72, remainingSteps: 3, state: "RUNNING", failedReason: null, retryUrl: "#/projects/p-2001/reviews" },
        ],
        activities: [
          { time: "2026-08-20T16:30:00+08:00", title: "补遗文件 v3 上传", desc: "采购人发布补遗，依赖 v1/v2 的要求与基线标记为待复核", kind: "warn" },
          { time: "2026-08-20T15:40:00+08:00", title: "审核链路任务启动", desc: "多 Agent 全审核链路进入 RUNNING", kind: "" },
          { time: "2026-08-20T11:20:00+08:00", title: "响应规划基线确认", desc: "赵明确认响应规划基线", kind: "" },
          { time: "2026-08-19T18:00:00+08:00", title: "章节初稿提交审核", desc: "提交 12 个章节初稿", kind: "" },
        ],
      },
      documents: {
        objects: [
          { id: "d-1", name: "招标文件（主）", type: "采购文件", source: "政府采购网", version: "v3", status: "ANALYZING", stale: false },
          { id: "d-2", name: "补遗通知 No.2", type: "补遗文件", source: "政府采购网", version: "v3", status: "ANALYZING", stale: false },
          { id: "d-3", name: "技术规范附件", type: "技术附件", source: "采购人", version: "v1", status: "STALE", stale: true },
          { id: "d-4", name: "澄清答复-投标人间", type: "澄清文件", source: "采购人", version: "v2", status: "PARSE_FAILED", stale: false },
        ],
        versions: [
          { id: "dv-1", objectId: "d-1", label: "v1 初始有效版本", time: "2026-08-12T10:00:00+08:00", state: "STALE", relation: "已被 v3 覆盖" },
          { id: "dv-2", objectId: "d-1", label: "v2 更正", time: "2026-08-15T14:00:00+08:00", state: "STALE", relation: "已被 v3 覆盖" },
          { id: "dv-3", objectId: "d-1", label: "v3 含补遗（当前有效）", time: "2026-08-20T16:00:00+08:00", state: "ANALYZING", relation: "有效" },
        ],
        segments: [
          { id: "seg-1", page: 12, path: "第三章/资格要求/3.1", text: "投标人须具有省级以上信息安全服务资质（有效期覆盖投标截止日）", source: "d-1 v3", structured: { type: "资格要求", risk: "BLOCK" } },
          { id: "seg-2", page: 28, path: "第五章/评分办法/2.1", text: "技术方案分 30 分，其中高可用架构 12 分", source: "d-1 v3", structured: { type: "评分项", risk: "MEDIUM" } },
          { id: "seg-3", page: 40, path: "第七章/商务要求/7.3", text: "运维响应时间不超过 2 小时", source: "d-1 v3", structured: { type: "实质性要求", risk: "HIGH" } },
        ],
        failed: { docId: "d-4", location: "第 3 页", reason: "扫描件倾斜超过阈值，OCR 无法稳定切分", retry: true, manual: true },
      },
      requirements: {
        items: [
          { id: "req-1", no: "Q-01", type: "资格条件", summary: "具有省级以上信息安全服务资质（有效期覆盖投标截止日）", page: 12, package: "采购包A", risk: "BLOCK", status: "待确认", owner: "资料管理员", section: "第2章 投标人资格", evidence: "证据不足" },
          { id: "req-2", no: "N-01", type: "否决项", summary: "投标保证金须在截止前到账", page: 9, package: "采购包A", risk: "HIGH", status: "已确认", owner: "商务/报价人员", section: "第5章 投标保证金", evidence: "已绑定" },
          { id: "req-3", no: "S-01", type: "实质性要求", summary: "运维响应时间不超过 2 小时", page: 40, package: "采购包A", risk: "HIGH", status: "待确认", owner: "技术方案人员", section: "第4章 技术方案", evidence: "证据待补充" },
          { id: "req-4", no: "T-01", type: "技术商务要求", summary: "高可用架构（双活）方案", page: 28, package: "采购包A", risk: "MEDIUM", status: "已确认", owner: "技术方案人员", section: "第4章 技术方案", evidence: "已绑定" },
          { id: "req-5", no: "M-01", type: "评分项", summary: "本地化服务团队（5 分）", page: 30, package: "采购包A", risk: "INFO", status: "已确认", owner: "标书编写人", section: "第4章 技术方案", evidence: "已绑定" },
          { id: "req-6", no: "D-01", type: "时间节点", summary: "投标截止 2026-09-15 17:00", page: 3, package: "采购包A", risk: "INFO", status: "已确认", owner: "投标经理", section: "第1章 投标须知", evidence: "—" },
        ],
        baseline: { confirmed: false, blockers: ["req-1"], highUnconfirmed: ["req-3"] },
      },
      responsePlan: {
        matrix: [
          { id: "rm-1", requirementNo: "Q-01", response: "提供资质证书复印件并承诺有效期覆盖", evidence: "证书-信息安全服务资质", owner: "资料管理员", status: "已绑定", scoreCover: "资格通过", historyDiff: "无差异" },
          { id: "rm-2", requirementNo: "S-01", response: "2 小时响应 SLA + 驻场团队", evidence: "运维SLA模板 v1", owner: "技术方案人员", status: "证据待补充", scoreCover: "实质性满足", historyDiff: "较参考项目差异：新增双活" },
          { id: "rm-3", requirementNo: "T-01", response: "双活高可用架构图与说明", evidence: "参考项目-交通云", owner: "技术方案人员", status: "已绑定", scoreCover: "12/12 分", historyDiff: "参考项目覆盖 10/12" },
          { id: "rm-4", requirementNo: "M-01", response: "本地服务团队名单与社保证明", evidence: "人员-本地团队", owner: "标书编写人", status: "已绑定", scoreCover: "5/5 分", historyDiff: "无差异" },
        ],
        baseline: { confirmed: true },
        references: [
          { id: "ref-1", name: "市交通数据治理平台（2025）", diff: "高可用架构得分 10/12，本方案 12/12" },
          { id: "ref-2", name: "区教育一体化平台（2024）", diff: "无驻场 SLA，本方案新增 2h 响应" },
        ],
      },
      authoring: {
        sections: [
          { id: "s-2210", title: "第1章 投标函及投标函附录", owner: "标书编写人", status: "已提交审核", progress: 100, risk: "INFO", locked: 2, blocks: 4 },
          { id: "s-2220", title: "第2章 投标人资格证明", owner: "资料管理员", status: "编制中", progress: 80, risk: "BLOCK", locked: 1, blocks: 6 },
          { id: "s-2230", title: "第4章 技术方案（高可用）", owner: "技术方案人员", status: "已提交审核", progress: 100, risk: "HIGH", locked: 3, blocks: 8 },
          { id: "s-2240", title: "第5章 项目实施方案", owner: "标书编写人", status: "编制中", progress: 60, risk: "MEDIUM", locked: 0, blocks: 7 },
        ],
        active: {
          id: "s-2230",
          title: "第4章 技术方案（高可用）",
          blocks: [
            { id: "b-1", type: "文本", title: "总体架构说明", locked: true, version: "v2", text: "采用同城双活 + 异地灾备的三中心架构，RPO<5s，RTO<30min。" },
            { id: "b-2", type: "图表", title: "高可用架构图", locked: false, version: "v2", text: "[架构图：双活数据中心 + 异地灾备]" },
            { id: "b-3", type: "表格", title: "SLA 指标表", locked: false, version: "v1", text: "响应时间 ≤2h；可用性 99.99%；故障恢复 ≤30min。" },
          ],
          references: [
            { id: "r-1", type: "要求", text: "S-01 运维响应时间不超过 2 小时", source: "招标文件 p40" },
            { id: "r-2", type: "评分项", text: "高可用架构 12 分", source: "招标文件 p28" },
            { id: "r-3", type: "企业证据", text: "运维SLA模板 v1（有效期内）", source: "企业资料库" },
            { id: "r-4", type: "历史参考", text: "市交通数据治理平台（覆盖 10/12 分）", source: "历史参考项目" },
          ],
          generation: [
            { id: "g-1", time: "2026-08-19T10:00:00+08:00", by: "章节草稿生成", version: "v1" },
            { id: "g-2", time: "2026-08-19T18:00:00+08:00", by: "人工锁定后重写", version: "v2" },
          ],
        },
        draftBaseline: { confirmed: false },
      },
      reviews: {
        summary: { total: 6, open: 3, resolved: 3, high: 2, block: 1 },
        issues: [
          { id: "ri-3301", domain: "资格", type: "证据不足", risk: "BLOCK", desc: "信息安全服务资质有效期至 2026-08-30，未覆盖投标截止日 2026-09-15", sourceReq: "Q-01", impactSection: "第2章 投标人资格证明", owner: "资料管理员", status: "待处理", round: 1, history: ["提交：证据有效期不足"] },
          { id: "ri-3302", domain: "技术", type: "一致性", risk: "HIGH", desc: "架构图中未体现异地灾备节点，与正文描述不一致", sourceReq: "T-01", impactSection: "第4章 技术方案", owner: "技术方案人员", status: "已退回", round: 1, history: ["提交：图实不符", "退回：补充灾备节点"] },
          { id: "ri-3303", domain: "商务", type: "报价", risk: "MEDIUM", desc: "运维费用明细与报价方案 v2 不一致", sourceReq: "N-01", impactSection: "第5章 报价", owner: "商务/报价人员", status: "复核中", round: 2, history: ["提交：金额差异", "修改：统一口径", "复核中"] },
          { id: "ri-3304", domain: "合规", type: "承诺", risk: "INFO", desc: "承诺函模板版本较新，建议使用启用版本", sourceReq: "S-01", impactSection: "第6章 承诺函", owner: "合规/法务人员", status: "已关闭", round: 1, history: ["提交", "复核关闭"] },
        ],
        risks: [
          { id: "rk-1", requirement: "Q-01", level: "BLOCK", desc: "资质有效期不足", acceptance: null, exemptBy: null },
          { id: "rk-2", requirement: "S-01", level: "HIGH", desc: "响应时间承诺证据待补充", acceptance: null, exemptBy: null },
        ],
        consistency: [
          { id: "c-1", area: "报价一致性", result: "存在差异", detail: "运维费用明细与报价方案 v2 不一致", status: "待复核" },
          { id: "c-2", area: "资质一致性", result: "通过", detail: "资质名称与要求一致", status: "已复核" },
        ],
        resultBaseline: { confirmed: false },
      },
      handover: {
        chain: [
          { key: "审核结果确认", state: "block", note: "存在未解决阻断风险，不可确认" },
          { key: "交接门禁", state: "block", note: "阻断风险未解决或未经授权豁免" },
          { key: "Handover Baseline", state: "pending", note: "待审核结果确认后建立" },
          { key: "DOCX/PDF 交接包", state: "pending", note: "待基线建立后生成" },
          { key: "递交责任人接收", state: "pending", note: "待交接包生成" },
          { key: "人工外部递交登记", state: "pending", note: "不自动连接电子交易平台" },
          { key: "回执上传", state: "pending", note: "人工上传回执" },
        ],
        versions: { sections: "v2", requirements: "v3", quotation: "报价方案 v2", review: "审核轮次 2", files: "v3" },
        fileList: [
          { name: "投标文件正本.docx", hash: "sha256:9f2a…c41b", export: "待生成" },
          { name: "报价一览表.pdf", hash: "sha256:1b7e…22d0", export: "待生成" },
        ],
        blockRisks: 1,
        unconfirmedGates: ["审核结果确认"],
        receiver: "王强（投标递交责任人）",
        packageTask: null,
        receivedAt: null,
        submission: { state: "未登记", receipt: null },
      },
      records: {
        events: [
          { id: "ev-1", time: "2026-08-20T16:30:00+08:00", type: "版本变化", actor: "系统", object: "采购文件", version: "v3", desc: "补遗文件触发 v1/v2 失效" },
          { id: "ev-2", time: "2026-08-20T11:20:00+08:00", type: "人工确认", actor: "赵明", object: "响应规划基线", version: "v1", desc: "确认响应规划基线" },
          { id: "ev-3", time: "2026-08-19T18:00:00+08:00", type: "退回", actor: "商务审核人员", object: "审核问题 ri-3302", version: "—", desc: "图实不符，退回修改" },
          { id: "ev-4", time: "2026-08-19T18:00:00+08:00", type: "审核", actor: "审核链路", object: "章节初稿", version: "v2", desc: "多 Agent 审核完成" },
          { id: "ev-5", time: "2026-08-19T10:00:00+08:00", type: "交接", actor: "—", object: "—", version: "—", desc: "尚未进入交接" },
          { id: "ev-6", time: "2026-08-19T10:00:00+08:00", type: "递交", actor: "—", object: "—", version: "—", desc: "尚未登记人工递交" },
          { id: "ev-7", time: "2026-08-12T10:00:00+08:00", type: "审计", actor: "系统", object: "项目创建", version: "—", desc: "项目与采购包创建，审计事件写入" },
        ],
      },
    },
  },

  /* GET /api/v1/projects/{id}/knowledge (企业资料库为独立页面，此处为引用列表) */
  knowledge: [
    { id: "k-1", name: "信息安全服务资质证书", category: "资质", subject: "本单位", validTo: "2026-08-30", scope: "全国", permission: "公开", source: "资料管理员上传", state: "EXPIRED", note: "有效期至 2026-08-30，未覆盖投标截止日，不可作为可用证据" },
    { id: "k-2", name: "ISO27001 证书", category: "资质", subject: "本单位", validTo: "2027-05-01", scope: "全国", permission: "公开", source: "资料管理员上传", state: "可用", note: "有效期内" },
    { id: "k-3", name: "项目经理-张工", category: "人员", subject: "张工", validTo: "2026-12-31", scope: "本项目", permission: "项目内", source: "资料管理员上传", state: "可用", note: "社保证明已附" },
    { id: "k-4", name: "2024 年度运维业绩合同", category: "业绩", subject: "本单位", validTo: "2026-12-31", scope: "类似项目", permission: "项目内", source: "资料管理员上传", state: "主体不符", note: "签约主体为子公司，与投标主体不一致" },
    { id: "k-5", name: "运维SLA模板 v1", category: "证明材料", subject: "本单位", validTo: "2027-01-01", scope: "全国", permission: "公开", source: "模板库", state: "可用", note: "有效期内" },
  ],

  templatesRules: {
    templates: [
      { id: "tpl-1", name: "政务云投标书模板", version: "v3", state: "启用", updated: "2026-07-20" },
      { id: "tpl-2", name: "承诺函模板", version: "v2", state: "启用", updated: "2026-07-10" },
      { id: "tpl-3", name: "报价一览表模板", version: "v1", state: "测试中", updated: "2026-08-01" },
      { id: "tpl-4", name: "技术方案空白模板", version: "v4", state: "草稿", updated: "2026-08-15" },
    ],
    ruleSets: [
      { id: "rs-1", name: "资格否决规则集", version: "v2", state: "启用", note: "启用新版本不改写历史项目使用的版本" },
      { id: "rs-2", name: "评分覆盖规则集", version: "v1", state: "停用", note: "被 v2 替代" },
    ],
    glossary: [
      { id: "gl-1", term: "实质性要求", def: "不满足即导致投标被否决的要求" },
      { id: "gl-2", term: "阻断风险", def: "必须解决或经授权豁免后方可继续推进的风险" },
    ],
  },

  admin: {
    users: [
      { id: "u-1001", name: "赵明", account: "zhaoming", role: "投标经理/项目负责人", enabled: true },
      { id: "u-1002", name: "李红", account: "lihong", role: "标书编写人", enabled: true },
      { id: "u-1003", name: "王强", account: "wangqiang", role: "投标递交责任人", enabled: true },
      { id: "u-1004", name: "前员工-陈", account: "chen", role: "资料管理员", enabled: false },
    ],
    services: [
      { id: "sv-1", name: "模型服务（生成）", health: "正常", queue: 3, lastFail: "—" },
      { id: "sv-2", name: "解析服务", health: "1 个失败任务", queue: 1, lastFail: "2026-08-20T14:22" },
      { id: "sv-3", name: "检索服务（BM25+向量+重排）", health: "正常", queue: 0, lastFail: "—" },
    ],
    security: [
      { id: "sec-1", type: "Session", desc: "赵明 的 Session 有效", time: "2026-08-20T19:00" },
    ],
  },
};

window.MockData = MockData;
window.ROLES = ROLES;
window.RISK_LEVELS = RISK_LEVELS;
window.statusBadge = statusBadge;
window.riskBadge = riskBadge;
window.statusMeta = statusMeta;
