# -*- coding: utf-8 -*-
"""分类体系与打分规则（离线规则引擎）。"""

# 默认分类体系：名称 -> (关键词, 说明)
TAXONOMY = {
    "01_专业建设与发展": {
        "desc": "专业申报、人才培养方案、专业认证与评估、专业规划",
        "keywords": [
            "专业建设", "人才培养方案", "培养方案", "专业认证", "专业评估",
            "专业申报", "新专业", "专业设置", "一流专业", "特色专业",
            "专业群", "工程教育认证", "培养目标", "毕业要求", "专业调研",
        ],
    },
    "02_课程与教材": {
        "desc": "课程大纲、课程标准、教材建设与选用、课程改革",
        "keywords": [
            "课程大纲", "教学大纲", "课程标准", "教材", "讲义", "教案",
            "精品课程", "一流课程", "课程建设", "课程改革", "课程思政",
            "教学计划", "课时", "学分", "选用教材", "自编教材",
        ],
    },
    "03_学生学科竞赛": {
        "desc": "学生学科竞赛通知、获奖、组织方案",
        "keywords": [
            "学科竞赛", "竞赛通知", "获奖名单", "获奖", "参赛", "大赛",
            "创新创业大赛", "数学建模", "挑战杯", "互联网+", "技能大赛",
            "竞赛组织", "指导教师", "赛项", "晋级",
        ],
    },
    "04_学生专利论文": {
        "desc": "学生专利、学生论文、大创项目成果",
        "keywords": [
            "专利", "发明", "实用新型", "软件著作权", "学生论文",
            "大创", "大学生创新创业训练", "成果", "授权", "申请号",
        ],
    },
    "05_教师教学竞赛": {
        "desc": "教师教学比赛、教学能力大赛",
        "keywords": [
            "教学竞赛", "教学比赛", "教学能力大赛", "讲课比赛", "青年教师",
            "教学基本功", "说课", "微课比赛", "教师参赛",
        ],
    },
    "06_教研论文与课题": {
        "desc": "教改论文、教研课题、教改项目",
        "keywords": [
            "教改", "教研", "课题", "立项", "结题", "中期检查",
            "教改项目", "研究论文", "教改论文", "项目申报书", "研究成果",
        ],
    },
    "07_产教融合与校企合作": {
        "desc": "校企合作、实习基地、产业学院、产学研",
        "keywords": [
            "校企合作", "产教融合", "实习基地", "产业学院", "产学研",
            "合作协议", "企业", "订单班", "现代学徒制", "实践基地", "协同育人",
        ],
    },
    "09_教学管理与运行": {
        "desc": "排课调课、成绩学籍、教学检查、日常教学运行",
        "keywords": [
            "排课", "调课", "课表", "成绩", "学籍", "选课", "考试",
            "教学检查", "教学运行", "监考", "重修", "教学任务",
            "教学管理", "开课", "教室", "督导",
        ],
    },
    "10_历年考核与评价": {
        "desc": "年度考核、绩效评价、教学质量评价、评优",
        "keywords": [
            "考核", "评价", "绩效", "评优", "年度考核", "教学质量评价",
            "师德", "考核表", "述职", "测评", "评教",
        ],
    },
    "11_行政综合文件": {
        "desc": "行政通知、规章制度、会议纪要、计划总结",
        "keywords": [
            "通知", "制度", "办法", "规定", "会议纪要", "工作计划",
            "工作总结", "请示", "报告", "批复", "函", "人事", "值班",
        ],
    },
    "移交实验室组": {
        "desc": "实验室建设、设备移交、实训室",
        "keywords": [
            "实验室", "实训室", "设备", "移交", "仪器", "耗材",
            "安全", "实验教学", "机房", "验收",
        ],
    },
}

# 文种词：命中即强提示
DOC_TYPE_HINTS = {
    "通知": "11_行政综合文件",
    "办法": "11_行政综合文件",
    "规定": "11_行政综合文件",
    "会议纪要": "11_行政综合文件",
    "申报书": None,
    "名单": None,
    "统计表": None,
    "总结": "11_行政综合文件",
}

_FILENAME_BOOST = 2.0     # 文件名命中权重（强提示）
_TITLE_BOOST = 1.5        # 文档开头区域命中权重
_BODY_BOOST = 1.0


def classify(text: str, filename: str = "", taxonomy: dict | None = None) -> list[dict]:
    """返回按得分排序的候选列表：[{name, score, matched, desc}]。"""
    tax = taxonomy or TAXONOMY
    name_l = (filename or "").lower()
    head = text[:600]
    body = text

    results = []
    for cat, meta in tax.items():
        score = 0.0
        matched = []
        for kw in meta["keywords"]:
            k = kw.lower()
            hit = False
            if k in name_l:
                score += _FILENAME_BOOST
                hit = True
            if k in head.lower():
                score += _TITLE_BOOST
                hit = True
            elif k in body.lower():
                score += _BODY_BOOST
                hit = True
            if hit:
                matched.append(kw)
        if score > 0:
            results.append({
                "name": cat,
                "score": round(score, 2),
                "matched": matched[:6],
                "desc": meta["desc"],
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def confidence(candidates: list[dict]) -> float:
    """0~1 的粗略置信度：看头名是否明显领先。"""
    if not candidates:
        return 0.0
    top = candidates[0]["score"]
    second = candidates[1]["score"] if len(candidates) > 1 else 0.0
    if top <= 0:
        return 0.0
    lead = (top - second) / top          # 领先幅度
    volume = min(top / 10.0, 1.0)        # 命中量
    return round(min(0.35 * volume + 0.65 * lead, 1.0), 2)
