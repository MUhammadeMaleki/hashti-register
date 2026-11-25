export type SessionInfo = {
  actor_type: "user" | "guest";
  actor_id: number;
  role: "super_admin" | "secretary" | null;
  must_change_password: boolean;
};

export class ApiError extends Error {
  constructor(public status: number, public code: string) {
    super(code);
  }
}

const messages: Record<string, string> = {
  invalid_credentials: "نام کاربری یا رمز عبور درست نیست.",
  invalid_session: "نشست شما پایان یافته است. دوباره وارد شوید.",
  account_locked: "حساب موقتاً قفل شده است. کمی بعد دوباره تلاش کنید.",
  account_inactive: "این حساب غیرفعال است.",
  account_exists: "برای این شماره قبلاً حساب ساخته شده است.",
  username_exists: "این نام کاربری قبلاً ثبت شده است.",
  invalid_registration: "اطلاعات ثبت‌نام را بررسی کنید.",
  invalid_password: "رمز عبور پذیرفته نشد.",
  weak_password: "رمز عبور باید دست‌کم ۱۲ نویسه باشد.",
  password_too_short: "رمز عبور باید دست‌کم ۱۲ نویسه باشد.",
  invalid_csrf: "نشست امنیتی نامعتبر است. صفحه را تازه کنید.",
  invalid_origin: "درخواست از مبدأ مجاز ارسال نشده است.",
  forbidden: "دسترسی به این بخش مجاز نیست.",
  event_number_exists: "این شمارهٔ هشتی قبلاً ثبت شده است.",
  exact_event_incomplete: "برای حالت دقیق، تاریخ، ساعت و مکان ذخیره‌شده را وارد کنید.",
  exact_time_incomplete: "برای زمان دقیق، تاریخ و ساعت شروع را وارد کنید.",
  approximate_time_incomplete: "برای زمان تقریبی، شرح زمان را وارد کنید.",
  exact_location_incomplete: "برای مکان دقیق، یک مکان ذخیره‌شده انتخاب کنید.",
  approximate_location_incomplete: "برای مکان تقریبی، محدودهٔ مکان را بنویسید.",
  approximate_event_incomplete: "برای حالت تقریبی، زمان یا محدودهٔ مکان را وارد کنید.",
  inactive_or_invalid_secretary: "همهٔ دبیران انتخاب‌شده باید فعال باشند.",
  secretary_required: "دست‌کم یک دبیر فعال برای رویداد انتخاب کنید.",
  entry_fee_has_registrations: "تغییر ورودی این رویداد به‌دلیل وجود ثبت‌نام فعلاً مجاز نیست.",
  event_has_history: "رویداد دارای سابقهٔ ثبت‌نام یا پرداخت است و حذف نمی‌شود.",
  location_has_events: "این مکان به رویداد متصل است و حذف نمی‌شود.",
  event_cancelled: "رویداد لغوشده در این بخش قابل ویرایش نیست.",
  invalid_poster_type: "نوع تصویر پذیرفته نیست؛ JPG، PNG، WebP یا HEIC/HEIF انتخاب کنید.",
  invalid_poster_size: "حجم پوستر باید کمتر از ۵ مگابایت باشد.",
  invalid_poster_image: "فایل تصویر معتبر نیست یا ابعاد آن بیش از حد مجاز است.",
  invalid_poster_dimensions: "ابعاد پوستر بیش از حد مجاز است.",
  invalid_phone: "شمارهٔ موبایل معتبر نیست.",
  guest_phone_exists: "برای این شماره موبایل قبلاً مخاطب ثبت شده است.",
  guest_has_history: "این مخاطب حساب یا سابقه دارد و حذف نمی‌شود.",
  guest_not_found: "مخاطب پیدا نشد.",
  tag_exists: "این برچسب قبلاً ساخته شده است.",
  invalid_interest_tag: "برچسب انتخاب‌شده معتبر نیست.",
  already_registered: "این مخاطب قبلاً در این رویداد ثبت‌نام کرده است.",
  registration_closed: "ثبت‌نام این رویداد بسته است.",
  registration_cancelled: "این ثبت‌نام لغو شده و حضور آن قابل تغییر نیست.",
  registration_not_cancelled: "این ثبت‌نام لغو نشده است.",
  attendance_back_to_pending: "بازگرداندن حضور به نامشخص مجاز نیست.",
  idempotency_payload_conflict: "این درخواست با کلید تکراری و اطلاعات متفاوت ارسال شده است.",
  wallet_ledger_mismatch: "موجودی کیف پول با دفتر مالی هم‌خوانی ندارد؛ بررسی مدیریتی لازم است.",
  order_attendance_not_allowed: "برای حضور نامشخص یا غیبت بدون هزینه، ثبت سفارش مجاز نیست.",
  order_cancelled: "سفارش لغوشده قابل ویرایش یا لغو دوباره نیست.",
  order_not_found: "سفارش پیدا نشد.",
  insufficient_balance: "موجودی کیف پول برای این برداشت یا تسویه کافی نیست.",
  settlement_exceeds_debt: "مبلغ تسویه از بدهی این رویداد بیشتر است.",
  settlement_not_allowed: "تسویهٔ ثبت‌نام یا رویداد لغوشده مجاز نیست.",
  refund_exceeds_settlement: "مبلغ برگشت از تسویهٔ فعال بیشتر است.",
  settlement_not_found: "تسویهٔ اصلی پیدا نشد.",
  settlement_operation_not_found: "نوبت تسویه پیدا نشد. فهرست را تازه کنید.",
  invalid_settlement_operation: "اطلاعات این نوبت تسویه ناسازگار است؛ بررسی مدیریتی لازم است.",
  settlement_already_cancelled: "این نوبت تسویه قبلاً کامل برگشت خورده است.",
  settlement_cancellation_not_allowed: "لغو تسویهٔ ثبت‌نام یا هشتی لغوشده مجاز نیست.",
  invalid_cancellation_reason: "دلیل لغو تسویه الزامی است.",
  invalid_adjustment: "مبلغ غیرصفر و توضیح برای اصلاح کیف پول الزامی است.",
  invalid_receipt_type: "نوع تصویر پذیرفته نیست؛ JPG، PNG، WebP یا HEIC/HEIF انتخاب کنید.",
  invalid_receipt_size: "حجم تصویر نباید از ۵ مگابایت بیشتر باشد.",
  invalid_receipt_image: "تصویر رسید معتبر نیست یا ابعاد آن بیش از حد مجاز است.",
  payment_evidence_required: "کد پیگیری یا تصویر رسید لازم است.",
  active_registration_required: "برای ثبت رسید این رویداد، ثبت‌نام فعال لازم است.",
  payment_not_found: "رسید پیدا نشد یا دسترسی به آن ندارید.",
  invalid_import_file: "فایل XLSX معتبر انتخاب کنید.",
  invalid_import_size: "حجم فایل یا تعداد ردیف‌ها بیش از حد مجاز است.",
  invalid_import_columns: "ستون‌های فایل معتبر نیستند؛ از فایل نمونه استفاده کنید.",
  invalid_import_preview: "پیش‌نمایش منقضی شده یا فایل تغییر کرده است؛ دوباره بررسی کنید.",
  payment_already_reviewed: "این رسید قبلاً بررسی شده است. فهرست را تازه کنید.",
  invalid_reject_reason: "دلیل رد بیش از حد طولانی است.",
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return messages[error.code] ?? (error.status === 422
      ? "اطلاعات واردشده معتبر نیست."
      : "درخواست انجام نشد. دوباره تلاش کنید.");
  }
  return "ارتباط با سرور برقرار نشد. اتصال خود را بررسی کنید.";
}

function csrfToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const entry = document.cookie.split("; ").find((part) => part.startsWith("hashti_csrf="));
  return entry ? decodeURIComponent(entry.slice("hashti_csrf=".length)) : undefined;
}

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return null;
  try { return await response.json(); } catch { return null; }
}

export async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(method)) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", token);
  }
  const response = await fetch(`/api${path}`, {
    ...options, method, headers, credentials: "same-origin", cache: "no-store",
  });
  if (response.status === 401 && retry &&
    (path === "/auth/session" || !path.startsWith("/auth/"))) {
    try {
      await api<{ status: string }>("/auth/refresh", { method: "POST" }, false);
      return api<T>(path, options, false);
    } catch { /* Return the original authentication error. */ }
  }
  const body = await readJson(response);
  if (!response.ok) {
    const code = body && typeof body === "object" && "detail" in body &&
      typeof body.detail === "string" ? body.detail : "request_failed";
    throw new ApiError(response.status, code);
  }
  return body as T;
}

export const auth = {
  session: () => api<SessionInfo>("/auth/session"),
  adminLogin: (username: string, password: string) =>
    api<{ actor_type: "user" }>("/auth/admin/login", {
      method: "POST", body: JSON.stringify({ username, password }),
    }),
  guestLogin: (phone: string, password: string) =>
    api<{ actor_type: "guest"; must_change_password: boolean }>("/auth/guest/login", {
      method: "POST", body: JSON.stringify({ phone, password }),
    }),
  guestRegister: (first_name: string, last_name: string, phone: string, password: string) =>
    api<{ guest_id: number; account_id: number }>("/auth/guest/register", {
      method: "POST", body: JSON.stringify({ first_name, last_name, phone, password }),
    }),
  logout: () => api<{ status: string }>("/auth/logout", { method: "POST" }),
  changeGuestPassword: (new_password: string) =>
    api<{ status: string }>("/auth/guest/change-password", {
      method: "POST", body: JSON.stringify({ new_password }),
    }),
  changeAdminPassword: (current_password: string, new_password: string) =>
    api<{ status: string }>("/auth/admin/change-password", {
      method: "POST", body: JSON.stringify({ current_password, new_password }),
    }),
};
