/**
 * JS mirror of expo-app/backend/notify.py `is_official_law_or_direction`.
 *
 * Kept in a small module so it can be reused by any Cloud Function that
 * needs to classify a pending_content_change / notifications_draft doc
 * against the "laws and official directions only" rule.
 */

const OFFICIAL_SOURCE_DOMAINS = [
  "homeaffairs.gov.au",
  "immi.homeaffairs.gov.au",
  "immigration.homeaffairs.gov.au",
  "border.gov.au",
  "aat.gov.au",
  "dfat.gov.au",
  "servicesaustralia.gov.au",
  "treasury.gov.au",
  "legislation.gov.au",
  "abs.gov.au",
  "jobsandskills.gov.au",
  "nsw.gov.au",
  "vic.gov.au",
  "qld.gov.au",
  "wa.gov.au",
  "sa.gov.au",
  "tas.gov.au",
  "act.gov.au",
  "nt.gov.au",
  "business.gov.au",
  "migration.wa.gov.au",
  "migration.tas.gov.au",
  "migration.sa.gov.au",
  "migration.qld.gov.au",
  "migration.nsw.gov.au",
  "liveinmelbourne.vic.gov.au",
  "canberrayourfuture.com.au",
  "vetassess.com.au",
  "engineersaustralia.org.au",
  "acs.org.au",
  "cpaaustralia.com.au",
  "cahpc.com.au",
  "ahpra.gov.au",
  "tra.gov.au",
  "nati.com.au",
  "nmba.gov.au",
  "theterritory.com.au",
];

const OFFICIAL_SCRAPER_SOURCE_PREFIXES = [
  "home_affairs",
  "homeaffairs",
  "visa_fee_",
  "processing_time_",
  "state_",
  "state_nomination",
  "anzsco_",
  "assessment_fee_",
  "policy_update",
  "skillselect_",
  "invitation_round",
  "legislative_instrument",
  "vetassess",
  "engineers_australia",
  "acs_",
  "cpa_",
  "ahpra_",
  "tra_",
  "skills_assessment",
  "authority_fee",
  "ministerial_direction",
];

const OFFICIAL_CONTENT_TYPES = new Set([
  "visa_fees",
  "assessment_fees",
  "processing_times",
  "skillselect_rounds",
  "state_nominations",
  "anzsco",
  "policy_update",
  "visa_change",
]);

const NEWS_CATEGORIES = new Set([
  "News",
  "Visa & Migration",
  "SkillSelect",
  "Occupation Lists",
  "Visa Fees",
  "System Update",
  "Visa Conditions",
  "Citizenship",
  "How to Apply",
]);

const CATEGORY_TO_CONTENT_TYPE = {
  "Processing Time": "processing_times",
  "SkillSelect Round": "skillselect_rounds",
  "Points Test": "policy_update",
  "Policy Update": "policy_update",
  "Visa Change": "visa_change",
  "Visa Fee Update": "visa_fees",
  "Assessment Fee Update": "assessment_fees",
  "Auto Fee Update": "assessment_fees",
  "ANZSCO Occupation List": "anzsco",
  "ANZSCO Classification": "anzsco",
  "State Nomination": "state_nominations",
};

const LAWS_AND_DIRECTIONS_KEYWORDS = [
  "legislative instrument",
  "ministerial direction",
  "migration act",
  "migration regulation",
  "migration regulations",
  "regulation change",
  "gazette",
  "explanatory statement",
  "fee schedule",
  "visa application charge",
  "visa fee",
  "fee increase",
  "fee change",
  "processing time",
  "invitation round",
  "skillselect round",
  "points threshold",
  "cutoff score",
  "cut-off score",
  "occupation list",
  "csol",
  "mltssl",
  "stsol",
  "rol",
  "anzsco",
  "nomination criteria",
  "nomination open",
  "nomination close",
  "nomination allocation",
  "nomination quota",
  "policy change",
  "visa change",
  "subclass 189",
  "subclass 190",
  "subclass 491",
  "subclass 482",
  "subclass 485",
  "subclass 186",
  "subclass 494",
  "subclass 500",
  "subclass 858",
  "home affairs announce",
  "department announce",
  "migration program planning",
  "migration program",
  "assessment fee",
  "skills assessment fee",
];

const PERSONAL_OR_STORY_MARKERS = [
  "share your story",
  "success story",
  "my story",
  "our story",
  "personal story",
  "case study",
  "testimonial",
  "op-ed",
  "opinion:",
  " opinion piece",
  "comment:",
  "column:",
  "editorial:",
  "how i ",
  "how we ",
  "my journey",
  "my experience",
  "our journey",
  "our experience",
  "tips for",
  "guide to",
  "guide for",
  "step-by-step guide",
  "what it's like",
  "what its like",
  "advice column",
  "profile:",
  "interview:",
  "q&a with",
  "q & a with",
  "explained:",
  "explainer:",
  "personal cost",
  "emotional weight",
  "family separation",
  "husband",
  "wife",
  "marriage story",
  "human compassion",
];

function domainFromUrl(url) {
  if (typeof url !== "string" || !url.trim()) return "";
  let lowered = url.trim().toLowerCase();
  if (lowered.startsWith("https://")) lowered = lowered.slice(8);
  else if (lowered.startsWith("http://")) lowered = lowered.slice(7);
  lowered = lowered.split("/")[0].split("?")[0];
  return lowered;
}

function hasOfficialDomain(url) {
  const host = domainFromUrl(url);
  if (!host) return false;
  return OFFICIAL_SOURCE_DOMAINS.some(
    (domain) => host === domain || host.endsWith("." + domain)
  );
}

function hasOfficialSourceId(sourceId) {
  if (typeof sourceId !== "string") return false;
  const lowered = sourceId.trim().toLowerCase();
  return OFFICIAL_SCRAPER_SOURCE_PREFIXES.some((prefix) => lowered.startsWith(prefix));
}

function textBlob(doc) {
  return [
    String(doc?.title || ""),
    String(doc?.body || ""),
    String(doc?.summary || ""),
    String(doc?.detectedValue || ""),
  ]
    .join(" ")
    .toLowerCase();
}

function isOfficialLawOrDirection(doc) {
  if (!doc || typeof doc !== "object") return false;
  const text = textBlob(doc);

  for (const marker of PERSONAL_OR_STORY_MARKERS) {
    if (text.includes(marker)) return false;
  }

  // Hard reject any item whose source_id looks like an RSS/news scraper even
  // if a human mis-categorised it. news_rss, state_news_scraper, rss_* etc.
  const sid = String(doc.source_id || doc.sourceId || doc.source || "").toLowerCase().trim();
  if (sid === "news_rss" || sid.startsWith("rss_") || sid.startsWith("news_rss") ||
      sid.includes("news_scraper") || sid === "scraper" || sid === "news") {
    return false;
  }

  // A trusted source is: an approved gov domain OR a structured scraper prefix.
  const sourceTrusted =
    hasOfficialDomain(doc.sourceUrl || doc.url) ||
    hasOfficialSourceId(doc.source_id || doc.sourceId || doc.source);

  if (!sourceTrusted) return false;

  const category = String(doc.category || "").trim();
  const derivedType = CATEGORY_TO_CONTENT_TYPE[category] || "";
  const explicitType = String(doc.contentType || "").trim();

  // Structured content types from a trusted source are accepted outright.
  if (OFFICIAL_CONTENT_TYPES.has(derivedType)) return true;
  if (OFFICIAL_CONTENT_TYPES.has(explicitType)) return true;

  // Trusted scraper source id without a structured contentType is still OK
  // because the scraper only produces structured diffs.
  if (hasOfficialSourceId(doc.source_id || doc.sourceId || doc.source)) return true;

  // Trusted gov domain but free-text: require a laws/directions keyword, and
  // reject News categories unless the keyword clearly matches.
  if (LAWS_AND_DIRECTIONS_KEYWORDS.some((kw) => text.includes(kw))) return true;
  if (category && !NEWS_CATEGORIES.has(category)) return true;
  return false;
}

function reasonWhyNotOfficial(doc) {
  if (!doc || typeof doc !== "object") return "empty document";
  const text = textBlob(doc);
  for (const marker of PERSONAL_OR_STORY_MARKERS) {
    if (text.includes(marker)) return `matches personal/story marker: "${marker}"`;
  }
  if (!hasOfficialDomain(doc.sourceUrl || doc.url) && !hasOfficialSourceId(doc.source_id || doc.sourceId || doc.source)) {
    return "source is not a recognised official gov domain or trusted scraper source_id";
  }
  return "no laws/directions keyword and category is generic News";
}

module.exports = {
  isOfficialLawOrDirection,
  reasonWhyNotOfficial,
  OFFICIAL_SOURCE_DOMAINS,
  OFFICIAL_SCRAPER_SOURCE_PREFIXES,
  OFFICIAL_CONTENT_TYPES,
  LAWS_AND_DIRECTIONS_KEYWORDS,
  PERSONAL_OR_STORY_MARKERS,
};
