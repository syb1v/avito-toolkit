export type Region = { slug: string; name: string };

// Слаг — как в URL Авито (/moskva?q=...). Список основных городов для выбора.
export const REGIONS: Region[] = [
  { slug: "moskva", name: "Москва" },
  { slug: "sankt-peterburg", name: "Санкт-Петербург" },
  { slug: "novosibirsk", name: "Новосибирск" },
  { slug: "ekaterinburg", name: "Екатеринбург" },
  { slug: "kazan", name: "Казань" },
  { slug: "nizhniy_novgorod", name: "Нижний Новгород" },
  { slug: "chelyabinsk", name: "Челябинск" },
  { slug: "samara", name: "Самара" },
  { slug: "omsk", name: "Омск" },
  { slug: "rostov-na-donu", name: "Ростов-на-Дону" },
  { slug: "ufa", name: "Уфа" },
  { slug: "krasnoyarsk", name: "Красноярск" },
  { slug: "voronezh", name: "Воронеж" },
  { slug: "perm", name: "Пермь" },
  { slug: "volgograd", name: "Волгоград" },
  { slug: "krasnodar", name: "Краснодар" },
  { slug: "saratov", name: "Саратов" },
  { slug: "tyumen", name: "Тюмень" },
  { slug: "tolyatti", name: "Тольятти" },
  { slug: "izhevsk", name: "Ижевск" },
  { slug: "barnaul", name: "Барнаул" },
  { slug: "ulyanovsk", name: "Ульяновск" },
  { slug: "irkutsk", name: "Иркутск" },
  { slug: "khabarovsk", name: "Хабаровск" },
  { slug: "yaroslavl", name: "Ярославль" },
  { slug: "vladivostok", name: "Владивосток" },
  { slug: "makhachkala", name: "Махачкала" },
  { slug: "tomsk", name: "Томск" },
  { slug: "orenburg", name: "Оренбург" },
  { slug: "kemerovo", name: "Кемерово" },
  { slug: "novokuznetsk", name: "Новокузнецк" },
  { slug: "ryazan", name: "Рязань" },
  { slug: "naberezhnye_chelny", name: "Набережные Челны" },
  { slug: "astrakhan", name: "Астрахань" },
  { slug: "penza", name: "Пенза" },
  { slug: "lipetsk", name: "Липецк" },
  { slug: "kirov", name: "Киров" },
  { slug: "cheboksary", name: "Чебоксары" },
  { slug: "balashikha", name: "Балашиха" },
  { slug: "kaliningrad", name: "Калининград" },
  { slug: "tula", name: "Тула" },
  { slug: "kursk", name: "Курск" },
  { slug: "sochi", name: "Сочи" },
  { slug: "stavropol", name: "Ставрополь" },
  { slug: "ulan-ude", name: "Улан-Удэ" },
  { slug: "tver", name: "Тверь" },
  { slug: "magnitogorsk", name: "Магнитогорск" },
  { slug: "ivanovo", name: "Иваново" },
  { slug: "bryansk", name: "Брянск" },
  { slug: "belgorod", name: "Белгород" },
  { slug: "surgut", name: "Сургут" },
  { slug: "vladimir", name: "Владимир" },
  { slug: "nizhniy_tagil", name: "Нижний Тагил" },
  { slug: "arkhangelsk", name: "Архангельск" },
  { slug: "chita", name: "Чита" },
  { slug: "smolensk", name: "Смоленск" },
  { slug: "kaluga", name: "Калуга" },
  { slug: "cherepovets", name: "Череповец" },
  { slug: "saransk", name: "Саранск" },
  { slug: "vologda", name: "Вологда" },
  { slug: "yakutsk", name: "Якутск" },
  { slug: "murmansk", name: "Мурманск" },
  { slug: "tambov", name: "Тамбов" },
  { slug: "petrozavodsk", name: "Петрозаводск" },
  { slug: "grozny", name: "Грозный" },
  { slug: "kostroma", name: "Кострома" },
  { slug: "novorossiysk", name: "Новороссийск" },
  { slug: "nizhnevartovsk", name: "Нижневартовск" },
  { slug: "yoshkar-ola", name: "Йошкар-Ола" },
  { slug: "oryol", name: "Орёл" },
  { slug: "sevastopol", name: "Севастополь" },
  { slug: "simferopol", name: "Симферополь" },
];


// Регионы-субъекты (Авито использует их в URL: /moskovskaya_oblast/...)
const REGION_SUBJECTS: Region[] = [
  { slug: "moskovskaya_oblast", name: "Московская область" },
  { slug: "leningradskaya_oblast", name: "Ленинградская область" },
  { slug: "krasnodarskiy_kray", name: "Краснодарский край" },
  { slug: "stavropolskiy_kray", name: "Ставропольский край" },
  { slug: "rostovskaya_oblast", name: "Ростовская область" },
  { slug: "sverdlovskaya_oblast", name: "Свердловская область" },
  { slug: "nizhegorodskaya_oblast", name: "Нижегородская область" },
  { slug: "samarskaya_oblast", name: "Самарская область" },
  { slug: "chelyabinskaya_oblast", name: "Челябинская область" },
  { slug: "novosibirskaya_oblast", name: "Новосибирская область" },
  { slug: "krasnoyarskiy_kray", name: "Красноярский край" },
  { slug: "altayskiy_kray", name: "Алтайский край" },
  { slug: "primorskiy_kray", name: "Приморский край" },
  { slug: "khabarovskiy_kray", name: "Хабаровский край" },
  { slug: "permskiy_kray", name: "Пермский край" },
  { slug: "zabaykalskiy_kray", name: "Забайкальский край" },
  { slug: "kamchatskiy_kray", name: "Камчатский край" },
  { slug: "kemerovskaya_oblast", name: "Кемеровская область" },
  { slug: "irkutskaya_oblast", name: "Иркутская область" },
  { slug: "omskaya_oblast", name: "Омская область" },
  { slug: "orenburgskaya_oblast", name: "Оренбургская область" },
  { slug: "voronezhskaya_oblast", name: "Воронежская область" },
  { slug: "saratovskaya_oblast", name: "Саратовская область" },
  { slug: "tyumenskaya_oblast", name: "Тюменская область" },
  { slug: "volgogradskaya_oblast", name: "Волгоградская область" },
  { slug: "tverskaya_oblast", name: "Тверская область" },
  { slug: "tulskaya_oblast", name: "Тульская область" },
  { slug: "yaroslavskaya_oblast", name: "Ярославская область" },
  { slug: "vladimirskaya_oblast", name: "Владимирская область" },
  { slug: "vologodskaya_oblast", name: "Вологодская область" },
  { slug: "belgorodskaya_oblast", name: "Белгородская область" },
  { slug: "bryanskaya_oblast", name: "Брянская область" },
  { slug: "kaliningradskaya_oblast", name: "Калининградская область" },
  { slug: "kaluzhskaya_oblast", name: "Калужская область" },
  { slug: "kostromskaya_oblast", name: "Костромская область" },
  { slug: "kurganskaya_oblast", name: "Курганская область" },
  { slug: "kurskaya_oblast", name: "Курская область" },
  { slug: "lipetskaya_oblast", name: "Липецкая область" },
  { slug: "magadanskaya_oblast", name: "Магаданская область" },
  { slug: "murmanskaya_oblast", name: "Мурманская область" },
  { slug: "novgorodskaya_oblast", name: "Новгородская область" },
  { slug: "orlovskaya_oblast", name: "Орловская область" },
  { slug: "penzenskaya_oblast", name: "Пензенская область" },
  { slug: "pskovskaya_oblast", name: "Псковская область" },
  { slug: "ryazanskaya_oblast", name: "Рязанская область" },
  { slug: "sakhalinskaya_oblast", name: "Сахалинская область" },
  { slug: "smolenskaya_oblast", name: "Смоленская область" },
  { slug: "tambovskaya_oblast", name: "Тамбовская область" },
  { slug: "tomskaya_oblast", name: "Томская область" },
  { slug: "ulyanovskaya_oblast", name: "Ульяновская область" },
  { slug: "arkhangelskaya_oblast", name: "Архангельская область" },
  { slug: "astrakhanskaya_oblast", name: "Астраханская область" },
  { slug: "ivanovskaya_oblast", name: "Ивановская область" },
  { slug: "kirovskaya_oblast_kirov", name: "Кировская область" },
  { slug: "amurskaya_oblast", name: "Амурская область" },
  { slug: "evreyskaya_avtonomnaya_oblast", name: "Еврейская автономная область" },
  { slug: "khanty-mansiyskiy_avtonomnyy_okrug", name: "Ханты-Мансийский АО" },
  { slug: "yamalo-nenetskiy_avtonomnyy_okrug", name: "Ямало-Ненецкий АО" },
  { slug: "nenetskiy_avtonomnyy_okrug", name: "Ненецкий АО" },
  { slug: "chukotskiy_avtonomnyy_okrug", name: "Чукотский АО" },
  { slug: "respublika_adygeya", name: "Республика Адыгея" },
  { slug: "respublika_altay", name: "Республика Алтай" },
  { slug: "bashkortostan", name: "Республика Башкортостан" },
  { slug: "respublika_buryatiya", name: "Республика Бурятия" },
  { slug: "dagestan", name: "Республика Дагестан" },
  { slug: "respublika_ingushetiya", name: "Республика Ингушетия" },
  { slug: "kabardino-balkariya", name: "Кабардино-Балкария" },
  { slug: "respublika_kalmykiya", name: "Республика Калмыкия" },
  { slug: "karachaevo-cherkesiya", name: "Карачаево-Черкесия" },
  { slug: "respublika_kareliya", name: "Республика Карелия" },
  { slug: "respublika_khakasiya", name: "Республика Хакасия" },
  { slug: "respublika_komi", name: "Республика Коми" },
  { slug: "krym", name: "Республика Крым" },
  { slug: "mariy_el", name: "Республика Марий Эл" },
  { slug: "respublika_mordoviya", name: "Республика Мордовия" },
  { slug: "sakha_yakutiya", name: "Республика Саха (Якутия)" },
  { slug: "respublika_osetiya_alaniya", name: "Республика Северная Осетия — Алания" },
  { slug: "tatarstan", name: "Республика Татарстан" },
  { slug: "respublika_tyva", name: "Республика Тыва" },
  { slug: "udmurtiya", name: "Удмуртская Республика" },
  { slug: "chechenskaya_respublika", name: "Чеченская Республика" },
  { slug: "chuvashiya", name: "Чувашская Республика" },
];

const SUBJECT_SUFFIXES: [RegExp, string][] = [
  [/avtonomnyy_okrug$/, "автономный округ"],
  [/avtonomnaya_oblast$/, "автономная область"],
  [/respublica$/, "республика"],
  [/oblast$/, "область"],
  [/kray$/, "край"],
];

function prettifySlug(slug: string): string {
  let value = slug.replace(/_/g, " ").replace(/-/g, " ");
  for (const [pattern, replacement] of SUBJECT_SUFFIXES) {
    if (pattern.test(slug)) {
      value = `${slug.split("_").slice(0, -1).join(" ")} ${replacement}`;
      break;
    }
  }
  const words = value
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1));
  return words.join(" ") || slug;
}

export const REGION_OPTIONS: Region[] = [...REGIONS, ...REGION_SUBJECTS];

const REGION_NAMES = new Map(REGION_OPTIONS.map((region) => [region.slug, region.name]));

export function regionName(slug: string | null | undefined): string {
  if (!slug) {
    return "все города";
  }
  return REGION_NAMES.get(slug) ?? prettifySlug(slug);
}


