/**
 * Bilingual copy: English and Bangla.
 *
 * Bangla is not a translation of the English here -- it is written to be read
 * naturally by a Bangla speaker. Verdict explanations especially: a literal
 * translation of "Unverified does not mean false" reads as legalese, so the
 * Bangla says it the way a person would.
 *
 * One source of truth, so a wording change cannot land in one language only.
 */

export type Locale = "en" | "bn";

export const LOCALES: { code: Locale; label: string; nativeLabel: string }[] = [
  { code: "en", label: "English", nativeLabel: "English" },
  { code: "bn", label: "Bangla", nativeLabel: "বাংলা" },
];

type Copy = Record<Locale, string>;

const t = (en: string, bn: string): Copy => ({ en, bn });

export const STRINGS = {
  // ---- Site chrome ------------------------------------------------------
  siteName: t("Evidence Check", "তথ্য যাচাই"),
  navRecent: t("Recent", "সাম্প্রতিক"),
  navMethod: t("Method", "পদ্ধতি"),
  skipToContent: t("Skip to main content", "মূল অংশে যান"),

  footerCoverage: t(
    "We report what the available evidence establishes. Coverage is limited to our indexed sources — we do not search the whole web, and we do not perform reverse image search.",
    "আমরা শুধু সেটুকুই বলি যতটুকু প্রাপ্ত তথ্যপ্রমাণ সমর্থন করে। আমাদের অনুসন্ধান কেবল নির্দিষ্ট কিছু সংবাদমাধ্যমে সীমাবদ্ধ — আমরা পুরো ইন্টারনেট খুঁজি না, ছবি দিয়ে উৎস খোঁজার সুবিধাও আমাদের নেই।",
  ),
  footerFallible: t(
    "Results can be wrong and can change as new evidence appears.",
    "ফলাফল ভুল হতে পারে, এবং নতুন তথ্য পাওয়া গেলে তা বদলাতেও পারে।",
  ),
  howThisWorks: t("How this works", "কীভাবে কাজ করে"),

  // ---- Home -------------------------------------------------------------
  heroTitle: t("What does the evidence say?", "তথ্যপ্রমাণ কী বলছে?"),
  heroSubtitle: t(
    "Submit a claim, article, image, or video. We find what evidence exists, show you what supports it and what contradicts it, and tell you plainly when we cannot establish an answer.",
    "যেকোনো দাবি, খবর, ছবি বা ভিডিও দিন। আমরা খুঁজে দেখি কী তথ্যপ্রমাণ আছে, কোনটি দাবিটিকে সমর্থন করে আর কোনটি বিরোধিতা করে — আর উত্তর না পেলে সেটাও স্পষ্ট করে বলি।",
  ),
  honestyNote: t(
    "We do not search the entire web and we cannot do reverse image search. Every report names the sources we actually checked.",
    "আমরা পুরো ইন্টারনেট খুঁজি না, ছবি দিয়ে উৎস খোঁজাও সম্ভব নয়। প্রতিটি রিপোর্টে আমরা ঠিক কোন কোন উৎস দেখেছি তা উল্লেখ থাকে।",
  ),
  readMethod: t("Read the method", "পদ্ধতি দেখুন"),

  recentlyChecked: t("Recently checked", "সদ্য যাচাই করা"),
  inProgress: t("In progress", "চলমান"),
  recentSubtitle: t("Public verifications, newest first.", "সর্বশেষ যাচাইগুলো।"),
  inProgressSubtitle: t(
    "Submissions currently being checked.",
    "এই মুহূর্তে যেগুলো যাচাই করা হচ্ছে।",
  ),
  emptyRecent: t(
    "No verifications yet. Submit something above to create the first one.",
    "এখনো কোনো যাচাই হয়নি। উপরে কিছু জমা দিয়ে শুরু করুন।",
  ),

  heroKicker: t(
    "Independent public-interest verification",
    "স্বাধীন জনস্বার্থে তথ্য যাচাই",
  ),
  heroLine1: t("Check the claim.", "দাবিটি যাচাই করুন।"),
  heroLine2: t("See the evidence.", "প্রমাণ দেখুন।"),
  heroPitch: t(
    "Submit a claim, article, or a captioned image or video. We find what evidence exists, show you what supports it and what contradicts it, and tell you plainly when we cannot establish an answer.",
    "যেকোনো দাবি, খবর, কিংবা ক্যাপশনসহ ছবি বা ভিডিও দিন। আমরা খুঁজে দেখি কী তথ্যপ্রমাণ আছে, কোনটি দাবিটিকে সমর্থন করে আর কোনটি বিরোধিতা করে — আর উত্তর না পেলে সেটাও স্পষ্ট করে বলি।",
  ),
  badgeSources: t("Sources shown", "উৎস দেখানো হয়"),
  badgeVerdicts: t("Verdicts explained", "সিদ্ধান্তের ব্যাখ্যা"),
  badgeNoAccount: t("No account", "অ্যাকাউন্ট লাগে না"),
  asideTagline: t("Not rumour,\nsee the evidence.", "গুজব নয়,\nপ্রমাণ দেখুন।"),
  asideBody: t(
    "Built for the stories, posts, images and conversations that shape Bangladesh.",
    "বাংলাদেশের যে খবর, পোস্ট, ছবি আর আলোচনা মানুষের ভাবনা গড়ে — সেগুলোর জন্যই তৈরি।",
  ),
  startCheck: t("Start a check", "যাচাই শুরু করুন"),
  whatToVerify: t("What would you like to verify?", "আপনি কী যাচাই করতে চান?"),
  privacyHint: t(
    "Private details? Remove them before submitting.",
    "ব্যক্তিগত তথ্য থাকলে জমা দেওয়ার আগে সরিয়ে ফেলুন।",
  ),
  textToVerify: t("Text to verify", "যাচাই করার লেখা"),
  linkToVerify: t("Link to verify", "যাচাই করার লিংক"),
  pasteFullUrl: t("Paste the complete public URL.", "সম্পূর্ণ পাবলিক লিংকটি দিন।"),
  bothLanguages: t(
    "Bangla and English are supported.",
    "বাংলা ও ইংরেজি — দুটোই চলবে।",
  ),
  checkThisClaim: t("Check this claim", "যাচাই করুন"),
  allVerifications: t("All verifications", "সব যাচাই"),
  recentPageTitle: t("Recent verifications", "সাম্প্রতিক যাচাই"),
  recentPageSubtitle: t(
    "Every submission is public. These are the most recent.",
    "প্রতিটি জমা সবাই দেখতে পায়। এগুলো সবচেয়ে সাম্প্রতিক।",
  ),

  // ---- Composer ---------------------------------------------------------
  tabText: t("Text", "লেখা"),
  tabLink: t("Link", "লিংক"),
  tabImage: t("Image", "ছবি"),
  tabVideo: t("Video", "ভিডিও"),
  verifyButton: t("Verify", "যাচাই করুন"),
  verifying: t("Submitting…", "জমা হচ্ছে…"),
  placeholderText: t(
    "Paste a claim, headline, article, or social post you want checked…",
    "যে দাবি, শিরোনাম, খবর বা পোস্টটি যাচাই করতে চান তা এখানে দিন…",
  ),
  noAccountNeeded: t(
    "No account needed. Results are public.",
    "কোনো অ্যাকাউন্ট লাগবে না। ফলাফল সবাই দেখতে পাবে।",
  ),
  chooseImage: t("Choose an image", "ছবি বাছুন"),
  chooseVideo: t("Choose a video", "ভিডিও বাছুন"),
  captionLabel: t("Caption or context", "ক্যাপশন বা প্রসঙ্গ"),
  optional: t("(optional)", "(ঐচ্ছিক)"),
  captionHelp: t(
    "What is this said to show? We check the caption separately from the file itself.",
    "এটি কী দেখাচ্ছে বলে দাবি করা হচ্ছে? ফাইলটির পাশাপাশি ক্যাপশনটিও আমরা আলাদাভাবে যাচাই করি।",
  ),
  captionPlaceholder: t(
    "e.g. Flooding in Dhaka this week",
    "যেমন: এই সপ্তাহে ঢাকায় বন্যা",
  ),
  isScreenshot: t("This is a screenshot", "এটি একটি স্ক্রিনশট"),
  screenshotHelp: t(
    "We read the visible text and check the claim it shows. A screenshot is not proof the original post is genuine.",
    "আমরা ছবির লেখা পড়ে সেই দাবিটি যাচাই করি। তবে স্ক্রিনশট থাকা মানেই মূল পোস্টটি আসল, তা নয়।",
  ),
  removeFile: t("Remove selected file", "ফাইলটি সরান"),
  errorTooShort: t(
    "Enter at least a sentence so we have something to check.",
    "অন্তত একটি বাক্য লিখুন, নাহলে যাচাই করার মতো কিছু থাকে না।",
  ),
  errorNeedUrl: t(
    "Enter the full link, including https://",
    "সম্পূর্ণ লিংক দিন, https:// সহ।",
  ),
  errorRateLimited: t(
    "You have made several submissions recently. Please wait a little before trying again.",
    "আপনি অল্প সময়ে অনেকগুলো জমা দিয়েছেন। কিছুক্ষণ পর আবার চেষ্টা করুন।",
  ),
  errorGeneric: t(
    "Something went wrong submitting this. Please try again.",
    "জমা দিতে সমস্যা হয়েছে। আবার চেষ্টা করুন।",
  ),

  // ---- Progress ---------------------------------------------------------
  checkingSubmission: t("Checking this submission", "যাচাই করা হচ্ছে"),
  checkingSubtitle: t(
    "Each step below reflects real progress on our side.",
    "নিচের প্রতিটি ধাপ আমাদের আসল অগ্রগতি দেখাচ্ছে।",
  ),
  queuedSubtitle: t(
    "Your check is queued and will begin shortly.",
    "আপনার যাচাইটি সারিতে আছে, শীঘ্রই শুরু হবে।",
  ),
  couldNotComplete: t(
    "This check could not be completed",
    "যাচাইটি সম্পূর্ণ করা যায়নি",
  ),
  ofSteps: t("of", "এর মধ্যে"),

  // ---- Report -----------------------------------------------------------
  overallVerdict: t("Overall verdict", "সার্বিক সিদ্ধান্ত"),
  whatWasSubmitted: t("What was submitted", "যা জমা দেওয়া হয়েছে"),
  claimsWeChecked: t("Claims we checked", "যেসব দাবি যাচাই করা হয়েছে"),
  evidence: t("Evidence", "তথ্যপ্রমাণ"),
  supporting: t("Supporting", "সমর্থনকারী"),
  contradicting: t("Contradicting", "বিরোধী"),
  supportingEvidence: t("Supporting evidence", "সমর্থনকারী তথ্যপ্রমাণ"),
  contradictingEvidence: t("Contradicting evidence", "বিরোধী তথ্যপ্রমাণ"),
  whatRemainsUnknown: t("What remains unknown", "যা এখনো অজানা"),
  unknownSubtitle: t(
    "We could not settle these claims either way.",
    "এই দাবিগুলো সত্য না মিথ্যা, আমরা নিশ্চিত হতে পারিনি।",
  ),
  unverifiedNotFalse: t(
    "Unverified is not the same as false. It means the evidence available to us was not enough to decide.",
    "‘যাচাই করা যায়নি’ মানে ‘মিথ্যা’ নয়। এর মানে সিদ্ধান্ত নেওয়ার মতো যথেষ্ট তথ্যপ্রমাণ আমরা পাইনি।",
  ),
  noEvidenceFound: t(
    "We did not find any evidence for or against this submission.",
    "এই দাবির পক্ষে বা বিপক্ষে আমরা কোনো তথ্যপ্রমাণ পাইনি।",
  ),
  noEvidenceExplain: t(
    "That is a statement about our coverage, not about the claim. Absence of evidence is not evidence that something is false.",
    "এটি আমাদের অনুসন্ধানের সীমাবদ্ধতার কথা বলছে, দাবিটির সত্যতা নিয়ে নয়। প্রমাণ না পাওয়া মানেই সেটি মিথ্যা, তা নয়।",
  ),
  noEvidenceForClaim: t(
    "No evidence was found for this claim.",
    "এই দাবির জন্য কোনো তথ্যপ্রমাণ পাওয়া যায়নি।",
  ),
  limitationsHeading: t("Limitations in this check", "এই যাচাইয়ের সীমাবদ্ধতা"),
  howChecked: t("How this was checked", "কীভাবে যাচাই করা হয়েছে"),
  methodBody: t(
    "We break a submission into individually checkable claims, search our indexed sources for relevant passages, label each passage as supporting or contradicting, and compute the verdict with a fixed, published formula. The language model never decides the verdict.",
    "আমরা প্রতিটি জমাকে আলাদা আলাদা যাচাইযোগ্য দাবিতে ভাগ করি, নির্দিষ্ট সংবাদমাধ্যমে প্রাসঙ্গিক অংশ খুঁজি, প্রতিটি অংশকে সমর্থনকারী বা বিরোধী হিসেবে চিহ্নিত করি, এবং একটি নির্দিষ্ট নিয়মে সিদ্ধান্তে পৌঁছাই। কোনো এআই মডেল সিদ্ধান্ত নেয় না।",
  ),
  methodDedup: t(
    "Republished copies of one report are grouped and counted as a single source, so widespread repetition does not raise confidence on its own.",
    "একই খবর অনেক জায়গায় ছাপা হলে সেগুলোকে একটিই উৎস হিসেবে গণনা করা হয় — তাই বেশি জায়গায় প্রচার হলেই বিশ্বাসযোগ্যতা বাড়ে না।",
  ),
  checkedOn: t("Checked", "যাচাইয়ের তারিখ"),
  scoringVersion: t("Scoring version", "স্কোরিং সংস্করণ"),
  pipelineVersion: t("Pipeline version", "পাইপলাইন সংস্করণ"),
  retrievalVersion: t("Retrieval version", "অনুসন্ধান সংস্করণ"),
  copyLink: t("Copy link to this result", "এই ফলাফলের লিংক কপি করুন"),
  linkCopied: t("Link copied", "লিংক কপি হয়েছে"),
  sourceLink: t("Source", "উৎস"),
  captionSuppliedWith: t(
    "Caption supplied with this file",
    "ফাইলটির সঙ্গে দেওয়া ক্যাপশন",
  ),
  claimLabel: t("Claim", "দাবি"),
  sourcesChecked: t("Sources checked", "যেসব উৎস দেখা হয়েছে"),

  // ---- Failure ----------------------------------------------------------
  noResult: t("No result", "কোনো ফলাফল নেই"),
  failedHeading: t(
    "We could not complete this check",
    "আমরা এই যাচাইটি শেষ করতে পারিনি",
  ),
  failedBody: t(
    "Something went wrong on our side before we reached a conclusion. This is not a judgement about the submission — it does not mean the claim is false or true.",
    "সিদ্ধান্তে পৌঁছানোর আগেই আমাদের দিকে সমস্যা হয়েছে। এটি দাবিটি সম্পর্কে কোনো রায় নয় — এর মানে দাবিটি সত্য বা মিথ্যা, কোনোটাই নয়।",
  ),
  whatHappened: t("What happened", "কী হয়েছিল"),
  serviceUnreachable: t(
    "The verification service is not responding.",
    "যাচাই সেবাটি সাড়া দিচ্ছে না।",
  ),
} as const;

export type StringKey = keyof typeof STRINGS;

export function tr(key: StringKey, locale: Locale): string {
  return STRINGS[key][locale];
}

// ---------------------------------------------------------------------------
// Verdicts
// ---------------------------------------------------------------------------

/**
 * Verdict names and meanings in both languages.
 *
 * The Bangla meanings are written for a general reader, not translated
 * word-for-word. "UNVERIFIED does not mean false" is the single most important
 * sentence in the product, so it is phrased the way a person would say it.
 */
export const VERDICT_COPY: Record<string, { label: Copy; meaning: Copy }> = {
  VERIFIED: {
    label: t("Verified", "সত্য প্রমাণিত"),
    meaning: t(
      "Strong, independent evidence establishes this claim.",
      "একাধিক নির্ভরযোগ্য ও স্বাধীন উৎসের তথ্যপ্রমাণে দাবিটি সমর্থিত হয়েছে।",
    ),
  },
  LIKELY_TRUE: {
    label: t("Likely true", "সম্ভবত সত্য"),
    meaning: t(
      "The evidence supports this claim, but sourcing is thin or has minor gaps.",
      "তথ্যপ্রমাণ দাবিটিকে সমর্থন করছে, তবে উৎস কম বা কিছু ফাঁক রয়ে গেছে।",
    ),
  },
  PARTLY_TRUE: {
    label: t("Partly true", "আংশিক সত্য"),
    meaning: t(
      "The core of this claim holds up, but specific details are wrong or overstated.",
      "দাবিটির মূল কথা ঠিক আছে, তবে নির্দিষ্ট কিছু তথ্য ভুল বা বাড়িয়ে বলা হয়েছে।",
    ),
  },
  MISLEADING: {
    label: t("Misleading", "বিভ্রান্তিকর"),
    meaning: t(
      "The underlying facts are real, but the framing, timing, or context creates a false impression.",
      "ঘটনাগুলো সত্যি, কিন্তু যেভাবে বা যে সময়ের প্রসঙ্গে উপস্থাপন করা হয়েছে তা ভুল ধারণা তৈরি করে।",
    ),
  },
  UNVERIFIED: {
    label: t("Unverified", "যাচাই করা যায়নি"),
    meaning: t(
      "We could not find enough evidence to reach a conclusion. This does not mean the claim is false.",
      "সিদ্ধান্তে পৌঁছানোর মতো যথেষ্ট তথ্যপ্রমাণ আমরা পাইনি। এর মানে দাবিটি মিথ্যা, তা কিন্তু নয়।",
    ),
  },
  LIKELY_FALSE: {
    label: t("Likely false", "সম্ভবত মিথ্যা"),
    meaning: t(
      "Meaningful evidence contradicts this claim, though not conclusively.",
      "উল্লেখযোগ্য তথ্যপ্রমাণ দাবিটির বিরোধিতা করছে, তবে তা চূড়ান্ত নয়।",
    ),
  },
  FALSE: {
    label: t("False", "মিথ্যা"),
    meaning: t(
      "Strong, independent evidence directly contradicts this claim.",
      "একাধিক নির্ভরযোগ্য ও স্বাধীন উৎসের তথ্যপ্রমাণ সরাসরি দাবিটির বিরোধিতা করছে।",
    ),
  },
  SATIRE: {
    label: t("Satire", "ব্যঙ্গ"),
    meaning: t(
      "This originates from satire or parody. It is not a sincere factual assertion.",
      "এটি ব্যঙ্গ বা রম্য রচনা থেকে এসেছে — সত্যিকারের তথ্য হিসেবে বলা হয়নি।",
    ),
  },
  OPINION: {
    label: t("Opinion", "মতামত"),
    meaning: t(
      "This is a value judgement or prediction, not a factual claim that evidence can settle.",
      "এটি একটি মতামত বা ভবিষ্যদ্বাণী — তথ্যপ্রমাণ দিয়ে যাচাই করার মতো দাবি নয়।",
    ),
  },
};

export const CONFIDENCE_COPY: Record<string, { label: Copy; meaning: Copy }> = {
  LOW: {
    label: t("Low confidence", "কম নিশ্চয়তা"),
    meaning: t(
      "Based on limited evidence. Treat this result with caution.",
      "সীমিত তথ্যপ্রমাণের ভিত্তিতে। ফলাফলটি সতর্কতার সঙ্গে দেখুন।",
    ),
  },
  MEDIUM: {
    label: t("Medium confidence", "মাঝারি নিশ্চয়তা"),
    meaning: t(
      "Based on a reasonable body of evidence, with some gaps.",
      "যথেষ্ট তথ্যপ্রমাণের ভিত্তিতে, তবে কিছু ফাঁক রয়ে গেছে।",
    ),
  },
  HIGH: {
    label: t("High confidence", "উচ্চ নিশ্চয়তা"),
    meaning: t(
      "Based on substantial, independent, directly relevant evidence.",
      "একাধিক স্বাধীন ও সরাসরি প্রাসঙ্গিক তথ্যপ্রমাণের ভিত্তিতে।",
    ),
  },
};

export const RELATIONSHIP_COPY: Record<string, Copy> = {
  SUPPORTS: t("Supports", "সমর্থন করে"),
  CONTRADICTS: t("Contradicts", "বিরোধিতা করে"),
  NEUTRAL: t("Related, but does not settle this", "সম্পর্কিত, তবে নিষ্পত্তি করে না"),
  INSUFFICIENT: t("Not enough to judge", "সিদ্ধান্ত নেওয়ার মতো যথেষ্ট নয়"),
};

export const ORIGIN_COPY: Record<string, Copy> = {
  USER_TEXT: t("Submitted text", "জমা দেওয়া লেখা"),
  USER_CAPTION: t("Caption supplied with the media", "ফাইলের সঙ্গে দেওয়া ক্যাপশন"),
  ARTICLE_TEXT: t("Article body", "খবরের মূল অংশ"),
  SOCIAL_POST_TEXT: t("Social post", "সামাজিক মাধ্যমের পোস্ট"),
  VIDEO_TRANSCRIPT: t("Video transcript", "ভিডিওর কথ্য অংশ"),
  ON_SCREEN_TEXT: t("On-screen text", "পর্দায় দেখানো লেখা"),
  OCR_TEXT: t("Text read from the image", "ছবি থেকে পড়া লেখা"),
};

/** Degradation reasons, phrased so a reader learns something actionable. */
export const DEGRADATION_COPY: Record<string, Copy> = {
  evidence_retrieval_not_implemented: t(
    "Evidence retrieval is not yet available, so no sources were searched.",
    "তথ্যপ্রমাণ অনুসন্ধান এখনো চালু হয়নি, তাই কোনো উৎস খোঁজা হয়নি।",
  ),
  media_analysis_not_implemented: t(
    "Media analysis is not yet available, so the file was stored but not examined.",
    "ছবি বা ভিডিও বিশ্লেষণ এখনো চালু হয়নি — ফাইলটি সংরক্ষণ করা হয়েছে, কিন্তু পরীক্ষা করা হয়নি।",
  ),
  url_content_unavailable: t(
    "We could not read this page. It may be paywalled, private, removed, or blocking automated readers.",
    "পাতাটি আমরা পড়তে পারিনি। এটি হয়তো অর্থের বিনিময়ে পড়তে হয়, ব্যক্তিগত, মুছে ফেলা হয়েছে, বা স্বয়ংক্রিয় পাঠ বন্ধ করা আছে।",
  ),
  some_sources_unreachable: t(
    "Some news sources could not be reached, so coverage was narrower than usual.",
    "কিছু সংবাদমাধ্যমে পৌঁছানো যায়নি, তাই স্বাভাবিকের চেয়ে কম উৎস দেখা হয়েছে।",
  ),
  ollama_unavailable: t(
    "The local language model was unavailable, so claim extraction used rules only.",
    "স্থানীয় ভাষা মডেলটি পাওয়া যায়নি, তাই দাবি শনাক্তকরণ শুধু নিয়মভিত্তিকভাবে হয়েছে।",
  ),
  ocr_unavailable: t(
    "No OCR engine is installed, so text inside images could not be read.",
    "ছবির ভেতরের লেখা পড়ার সফটওয়্যার ইনস্টল করা নেই, তাই তা পড়া যায়নি।",
  ),
};

export function verdictCopy(verdict: string | null | undefined, locale: Locale) {
  // An absent verdict reads as UNVERIFIED, never as a negative finding.
  const entry = VERDICT_COPY[verdict ?? "UNVERIFIED"] ?? VERDICT_COPY.UNVERIFIED;
  return { label: entry.label[locale], meaning: entry.meaning[locale] };
}

export function confidenceCopy(band: string, locale: Locale) {
  const entry = CONFIDENCE_COPY[band] ?? CONFIDENCE_COPY.LOW;
  return { label: entry.label[locale], meaning: entry.meaning[locale] };
}

export function relationshipCopy(relationship: string, locale: Locale): string {
  return RELATIONSHIP_COPY[relationship]?.[locale] ?? relationship;
}

export function originCopy(origin: string, locale: Locale): string {
  return ORIGIN_COPY[origin]?.[locale] ?? origin;
}

export function degradationCopy(reason: string, locale: Locale): string {
  const known = DEGRADATION_COPY[reason];
  if (known) return known[locale];
  // Never leak a raw enum to a reader.
  return reason.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
