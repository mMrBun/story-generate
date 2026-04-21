from typing import Any

Category = dict[str, str]

CATEGORIES: list[Category] = [
    {"slug": "fairy_tale", "zh": "童话", "en": "Fairy Tales", "ja": "童話", "ko": "동화", "value_zh": "想象、惊喜和温和的奇遇", "value_en": "imagination, wonder, and gentle magical encounters"},
    {"slug": "prophecy", "zh": "预言", "en": "Prophecy", "ja": "予言", "ko": "예언", "value_zh": "看懂提醒、做出选择，并明白未来可以被善意改变", "value_en": "gentle foresight, wise choices, interpreting signs, and learning that the future can be shaped by kindness"},
    {"slug": "perseverance", "zh": "恒心", "en": "Perseverance", "ja": "忍耐", "ko": "끈기", "value_zh": "耐心、坚持和一点一点把事情做完", "value_en": "patience, persistence, and steady long-term effort"},
    {"slug": "wit", "zh": "机智", "en": "Wit", "ja": "機知", "ko": "재치", "value_zh": "用聪明办法解决问题，但不欺负、不捉弄别人", "value_en": "clever problem solving without tricking or hurting others"},
    {"slug": "unity", "zh": "团结", "en": "Unity", "ja": "団結", "ko": "단결", "value_zh": "一起商量、互相帮忙，并共同完成目标", "value_en": "cooperation, helping each other, and reaching a goal together"},
    {"slug": "reflection", "zh": "反省", "en": "Reflection", "ja": "反省", "ko": "성찰", "value_zh": "发现自己的小错误，愿意承认，并想办法改好", "value_en": "understanding mistakes, noticing feelings, and gently making things right"},
    {"slug": "sharing", "zh": "分享", "en": "Sharing", "ja": "分かち合い", "ko": "나눔", "value_zh": "把好东西和快乐分给别人，也学会照顾别人的感受", "value_en": "generosity, shared joy, and caring for others"},
    {"slug": "diligence", "zh": "勤奋", "en": "Diligence", "ja": "勤勉", "ko": "성실", "value_zh": "认真练习、踏实做事，把小事情做好", "value_en": "careful practice, steady work, and doing small things well"},
    {"slug": "courage", "zh": "勇气", "en": "Courage", "ja": "勇気", "ko": "용기", "value_zh": "面对小困难，敢尝试，也敢说真话", "value_en": "trying bravely, speaking honestly, and facing small difficulties"},
    {"slug": "warmth", "zh": "温馨", "en": "Warmth", "ja": "ぬくもり", "ko": "따뜻함", "value_zh": "家人、陪伴、安慰和被惦记的感觉", "value_en": "family, companionship, comfort, and emotional warmth"},
    {"slug": "respect", "zh": "尊重", "en": "Respect", "ja": "尊重", "ko": "존중", "value_zh": "尊重差异、边界、长辈、朋友和自然", "value_en": "respecting differences, boundaries, elders, friends, and nature"},
    {"slug": "confidence", "zh": "自信", "en": "Confidence", "ja": "自信", "ko": "자신감", "value_zh": "相信自己，接纳自己，并慢慢变得更勇敢", "value_en": "believing in oneself, self-acceptance, and gentle growth"},
    {"slug": "cherish", "zh": "珍惜", "en": "Cherish", "ja": "大切にする心", "ko": "소중히 여김", "value_zh": "珍惜时间、朋友、自然和已经拥有的东西", "value_en": "cherishing time, friendship, nature, and what one already has"},
]


def category_name_for_language(category: Category, language_code: str) -> str:
    if language_code == "zh-Hans":
        return category["zh"]
    if language_code == "ja":
        return category["ja"]
    if language_code == "ko":
        return category["ko"]
    return category["en"]


def source_category_meaning(category: Category, source_language: str) -> str:
    if source_language == "zh-Hans":
        return category["value_zh"]
    return category["value_en"]
