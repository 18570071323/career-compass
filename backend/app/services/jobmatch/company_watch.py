"""公司避雷与推荐清单（docs/07-§22，M7.11）。

- 种子数据：黑名单（有公开报道的事件，如星宇股份）+ 高精尖企业推荐（公开信息示例）
- 数据来自公开报道/社区投稿，仅供参考；来源留痕、可下架
- 幂等：按 (company, kind) 去重
"""
from __future__ import annotations

import logging

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import CompanyWatchlist

logger = logging.getLogger(__name__)

# (company, kind, industry, risk_level, reason, source_url, source)
WATCHLIST_SEED: list[tuple[str, str, str, str, str, str, str]] = [
    # ---------- 黑名单（有公开报道） ----------
    (
        "星宇股份",
        "blacklist",
        "汽车零部件",
        "高",
        "2026年8月被公开报道：要求约400名应届毕业生以「个人原因」离职，拒绝者被安排至流水线「拧螺丝」。",
        "https://finance.sina.com.cn/roll/2026-08-23/doc-inipkzxu6090875.shtml",
        "manual",
    ),
    # ---------- 高精尖企业推荐（公开信息示例，投递前请核实最新招聘） ----------
    ("中科飞测", "recommended", "半导体检测", "", "科创板上市，半导体量检测设备领军企业，研发投入高。", "", "manual"),
    ("中科酷原", "recommended", "量子计算", "", "武汉光谷量子计算企业，前沿赛道，高端人才需求旺盛。", "", "manual"),
    ("汇川技术", "recommended", "工业自动化", "", "国产工业自动化龙头（变频器/伺服/新能源电控），高精尖制造。", "", "manual"),
    ("北方华创", "recommended", "半导体设备", "", "国产半导体设备平台型龙头，卡脖子环节，研发岗价值高。", "", "manual"),
    ("大疆", "recommended", "无人机/AI", "", "全球消费级无人机霸主，硬件+算法双强，校招竞争激烈但含金量高。", "", "manual"),
    ("万华化学", "recommended", "新材料/化工", "", "全球 MDI 龙头，新材料平台型公司，研发与制造并重。", "", "manual"),
]

# 历史黑名单（2017-2021 校招毁约/裁员等事件，来自牛客网等社区公开讨论，用户整理导入）
# (company, kind, industry, risk_level, reason, source_url, source)
HISTORICAL_BLACKLIST: list[tuple[str, str, str, str, str, str, str]] = [
    ("竞技世界", "blacklist", "游戏", "高", "2021/03 提前实习后毁校招正式offer，不给转正。", "https://www.nowcoder.com", "community"),
    ("虎牙", "blacklist", "直播", "高", "2021/03 毁校招意向书。", "https://www.nowcoder.com", "community"),
    ("高顿教育", "blacklist", "教育", "高", "2021/01 校招毁约。", "https://www.nowcoder.com", "community"),
    ("多益网络", "blacklist", "游戏", "高", "2020/12 寄三方后被毁约；体检完取消offer。", "https://www.nowcoder.com", "community"),
    ("腾讯", "blacklist", "互联网", "高", "2020/10-12 意向书后岗位被取消，多轮面试无果；另有因不能提前实习被毁offer。", "https://www.nowcoder.com", "community"),
    ("西山居", "blacklist", "游戏", "高", "2020/10 毁实习生offer，欺骗实习生。", "https://www.nowcoder.com", "community"),
    ("转转网", "blacklist", "二手电商", "高", "2020/10-11 毁意向书。", "https://www.nowcoder.com", "community"),
    ("哔哩哔哩", "blacklist", "视频", "高", "2020/10 毁校招意向书。", "https://www.nowcoder.com", "community"),
    ("猫眼", "blacklist", "文娱", "中", "2020/10 宣传转正率99.9%，被指PUA校招实习生。", "https://www.nowcoder.com", "community"),
    ("中电53所", "blacklist", "电子", "高", "2020/10 利用三方漏洞毁约天津/哈尔滨地区意向书。", "https://www.nowcoder.com", "community"),
    ("华为", "blacklist", "通信", "中", "2020/10 大量面试后泡池子不录用（华为云CBU几乎不招人）。", "https://www.nowcoder.com", "community"),
    ("顺丰快运科技", "blacklist", "物流", "高", "2020/10 大量毁约意向书（原帖已删除）。", "https://www.nowcoder.com", "community"),
    ("海康威视", "blacklist", "安防", "高", "2020/10 校招毁签约通知。", "https://www.nowcoder.com", "community"),
    ("寒武纪", "blacklist", "AI芯片", "高", "2019-2020 毁意向书；抽奖面试直通卡后不安排面试。", "https://www.nowcoder.com", "community"),
    ("Oppo", "blacklist", "手机", "中", "2020/08 实习转正存在性别歧视（引发公关道歉）。", "https://www.nowcoder.com", "community"),
    ("旷视", "blacklist", "AI", "高", "2020/08 秋招offer提前实习后被告知工作不利，主动解约三方。", "https://www.nowcoder.com", "community"),
    ("招银网络科技", "blacklist", "金融科技", "中", "2020/07 被指外包公司，PUA应届生。", "https://www.nowcoder.com", "community"),
    ("盛趣游戏", "blacklist", "游戏", "高", "2020/07 毁三方，解约应届生。", "https://www.nowcoder.com", "community"),
    ("四维图新", "blacklist", "地图/汽车电子", "高", "2020/07 拿到毕业证第二天被通知解约三方。", "https://www.nowcoder.com", "community"),
    ("马蜂窝", "blacklist", "旅游", "高", "2020/06 20届应届生全部被毁约。", "https://www.nowcoder.com", "community"),
    ("e成科技", "blacklist", "HR SaaS", "高", "2020/04 毁约且拒绝赔偿。", "https://www.nowcoder.com", "community"),
    ("蘑菇街", "blacklist", "电商", "高", "2020/04 裁应届生。", "https://www.nowcoder.com", "community"),
    ("畅唐网络", "blacklist", "游戏", "高", "2020/04 裁应届生（校招40多人仅留4-5个）。", "https://www.nowcoder.com", "community"),
    ("万得", "blacklist", "金融数据", "高", "2020/04 毁约。", "https://www.nowcoder.com", "community"),
    ("追一科技", "blacklist", "AI", "高", "2020/03 违约三方并裁应届生。", "https://www.nowcoder.com", "community"),
    ("GrowingIO", "blacklist", "数据分析", "高", "2020/03 毁应届offer，应届生被优化。", "https://www.v2ex.com", "community"),
    ("平安智慧城", "blacklist", "金融科技", "高", "2020/02 毁应届生三方。", "https://www.nowcoder.com", "community"),
    ("比特大陆", "blacklist", "芯片", "高", "2020/01 毁约。", "https://www.nowcoder.com/discuss/398338", "community"),
    ("云从科技", "blacklist", "AI", "高", "2019/11 毁意向书。", "https://www.nowcoder.com", "community"),
    ("滴滴", "blacklist", "出行", "中", "2019/10 毁意向书，强制转岗变相劝退。", "https://www.nowcoder.com", "community"),
    ("小米", "blacklist", "互联网", "高", "2019/10 毁意向书（原帖已删除）。", "https://www.nowcoder.com", "community"),
    ("美团", "blacklist", "生活服务", "高", "2019/10 大量毁意向书，口头offer被毁。", "https://www.nowcoder.com", "community"),
    ("腾讯微保", "blacklist", "保险科技", "高", "2019/10 被曝大量毁秋招意向offer（官方辟谣帖已删）。", "https://xueqiu.com", "community"),
    ("Keep", "blacklist", "健身", "高", "2019/10 毁意向书。", "https://www.nowcoder.com", "community"),
    ("猎豹", "blacklist", "互联网", "高", "2019/10 校招毁约。", "https://www.nowcoder.com", "community"),
    ("银联商务", "blacklist", "金融支付", "高", "2019/11 毁意向书。", "https://www.nowcoder.com", "community"),
    ("阿里巴巴", "blacklist", "互联网", "高", "2019/09 毁意向书（当事人删帖）。", "https://www.nowcoder.com", "community"),
    ("VIPKID", "blacklist", "教育", "高", "2019/10 大规模劝退、毁意向书。", "https://www.nowcoder.com", "community"),
    ("金蝶", "blacklist", "企业软件", "高", "2019/10 撕毁非全日制offer。", "https://www.nowcoder.com", "community"),
    ("怪兽充电", "blacklist", "共享充电", "高", "2019/10 毁口头offer（OC）。", "https://www.nowcoder.com", "community"),
    ("广联达", "blacklist", "建筑软件", "高", "2019/10 毁两方。", "https://www.nowcoder.com", "community"),
    ("快手", "blacklist", "视频", "高", "2019/10 校招毁约。", "https://www.nowcoder.com", "community"),
    ("一起教育科技", "blacklist", "教育", "高", "2019/02 毁offer并骗实习。", "https://www.nowcoder.com", "community"),
    ("作业帮", "blacklist", "教育", "高", "2019/11 毁数十人意向书。", "https://www.nowcoder.com", "community"),
    ("哈啰出行", "blacklist", "出行", "高", "2019/11 毁意向书。", "https://www.nowcoder.com", "community"),
    ("微博杭州研究中心", "blacklist", "互联网", "高", "2019/10 毁意向书。", "https://www.nowcoder.com", "community"),
    ("浪潮", "blacklist", "IT/服务器", "中", "2019/09 扣实习生工资，存在性别歧视。", "https://www.nowcoder.com", "community"),
    ("京东", "blacklist", "电商", "高", "2019/04 毁约19届应届（回应称极少数并赔偿）。", "https://www.163.com", "community"),
    ("网易", "blacklist", "互联网", "高", "2018-2019 校招后暴力裁应届生。", "https://www.nowcoder.com", "community"),
    ("第四范式", "blacklist", "AI", "高", "2018/10 大规模毁offer/意向书。", "https://www.nowcoder.com", "community"),
    ("迈瑞医疗", "blacklist", "医疗器械", "高", "2018/12 大量解聘应届生。", "https://www.nowcoder.com", "community"),
    ("宜信", "blacklist", "金融科技", "中", "2018/11 正式offer变实习offer。", "https://www.zhihu.com", "community"),
    ("金山云", "blacklist", "云计算", "高", "2017/10 秋招收回offer。", "https://www.zhihu.com", "community"),
]

DISCLAIMER = "本清单信息来自公开报道与用户投稿，仅供参考，可能存在时效与准确性偏差；投递前请通过企业信息平台（企查查/天眼查等）自行核实。"


async def ensure_company_seed(session: AsyncSession) -> dict:
    """幂等灌入种子清单；返回 {added, skipped}。"""
    added = skipped = 0
    all_seed = WATCHLIST_SEED + HISTORICAL_BLACKLIST
    # 批量查重：一次查询现有 (company, kind) 集合，避免逐行 SELECT（单请求 52+ 次往返）
    keys = [(company, kind) for company, kind, *_ in all_seed]
    existing_rows = (
        (
            await session.execute(
                select(CompanyWatchlist.company, CompanyWatchlist.kind).where(
                    tuple_(CompanyWatchlist.company, CompanyWatchlist.kind).in_(keys)
                )
            )
        )
        .all()
    )
    existing = {(r[0], r[1]) for r in existing_rows}
    for company, kind, industry, risk, reason, url, source in all_seed:
        if (company, kind) in existing:
            skipped += 1
            continue
        session.add(
            CompanyWatchlist(
                company=company,
                kind=kind,
                industry=industry or None,
                risk_level=risk or None,
                reason=reason,
                source_url=url or None,
                source=source,
                status="active",
            )
        )
        added += 1
    await session.commit()
    return {"added": added, "skipped": skipped}
