# استقرار هشتی — الگوی Ubuntu/Debian بدون Docker

این‌ها نمونه‌اند و تا پیش از جایگزینی دامنه، گواهی، مسیرها و اجرای آزمایشی نباید روی production فعال شوند. دستورهای این صفحه روی سرور لینوکسی اجرا می‌شوند؛ اجرای محلی Windows جای آزمون استقرار را نمی‌گیرد.

## پیش‌نیاز و جداسازی

- یک کاربر سیستمی بدون دسترسی login به نام `hashti`، پوشهٔ releaseهای جدا در `/srv/hashti/releases/` و symlink اتمیک `/srv/hashti/current` بسازید. release و کد برای کاربر سرویس خواندنی ولی جز مسیر cache، غیرقابل‌نوشتن باشند.
- `/var/lib/hashti/uploads/{receipts,posters}` را خارج از release بسازید؛ مالک `hashti` و مجوز پوشه‌ها `0700` باشد. Nginx هرگز این مسیر را با `alias` یا `root` سرو نکند. رسید فقط از API مجوزدار خوانده می‌شود.
- `deploy/env.example` را با مقادیر واقعی در `/etc/hashti/hashti.env` قرار دهید (`root:hashti`، مجوز `0640`). `HASHTI_AUTH_SECRET` باید ۶۴ رقم hex تصادفی باشد. فایل env و رمز دیتابیس در Git یا backup عمومی قرار نگیرند. `HASHTI_UPLOADS_DIR` باید مسیر مطلق مشترک بین releaseها باشد.
- PostgreSQL فقط روی loopback یا شبکهٔ خصوصی گوش کند؛ پورت ۵۴۳۲ در firewall عمومی بسته، `pg_hba.conf` محدود به نقش/دیتابیس لازم و SCRAM باشد. نقش API حداقل دسترسی لازم را داشته باشد؛ نقش backup جداگانه و اتصال `pg_dump` با `PGPASSFILE` خصوصی تنظیم شود.
- TLS و دامنه را قبل از فعال‌سازی آماده کنید. `HASHTI_PUBLIC_ORIGIN` دقیقاً همان origin عمومی HTTPS باشد؛ CORS باز نکنید. فایل `nginx.conf.example` در context `http` نصب و دامنه/مسیر گواهی جایگزین شود. `nginx -t` باید موفق باشد. اگر پشت CDN هستید، `real_ip` را فقط برای IPهای معتبر CDN تنظیم کنید تا rate limit با IP واقعی کار کند.

## انتشار کنترل‌شده

1. وضعیت فعلی و نسخهٔ release را ثبت کنید؛ بکاپ دیتابیس و آپلودها را در پنجرهٔ بدون نوشتن یا با snapshot هماهنگ بگیرید. `deploy/backup.sh` به `HASHTI_BACKUP_DB`، `HASHTI_BACKUP_ROOT`، `HASHTI_UPLOADS_DIR` و متغیرهای امن libpq (`PGHOST`، `PGPORT`، `PGUSER`، `PGPASSFILE`) نیاز دارد. خود اسکریپت dump/list/checksum و زمان شروع/پایان را ثبت می‌کند؛ برای بکاپ روزانه نگهداری دوره‌ای، کپی رمزنگاری‌شدهٔ خارج سرور و هشدار شکست job را جدا تنظیم کنید.
2. release تازه را در پوشهٔ جدا کپی کنید. Python virtualenv و `pip install -r backend/requirements.txt`، سپس `npm ci` را همان release اجرا کنید. تست‌های ضروری Backend روی دیتابیس تست جدا، `npm test`، typecheck و lint را بگیرید. روی محیط انتشار `npm run build` را اجرا و نتیجه را ثبت کنید؛ build محلی موفق بوده، اما جای build روی محیط انتشار را نمی‌گیرد. مسیر `.next/cache` را برای کاربر `hashti` قابل‌نوشتن کنید.
3. تغییرات Migration و سازگاری با release قبلی را بازبینی کنید؛ با اتصال production فقط پس از بکاپ، از پوشهٔ `backend` دستور `alembic upgrade head` را اجرا کنید. Migration مخرب را بدون برنامهٔ مستقل اجرا نکنید.
4. symlink `current` را به release تازه تغییر دهید؛ unitهای `hashti-api.service` و `hashti-web.service` را در systemd نصب کنید، `daemon-reload` و restart کنترل‌شده بگیرید. لاگ‌ها و `/api/health` و `/api/health/ready` را از دامنهٔ HTTPS چک کنید؛ یک خواندن واقعی مجوزدار را با حساب آزمایشی انجام دهید. هیچ نشست Uvicorn/Next محلی در این مرحله لازم نیست.
5. `nginx -t` و سپس reload؛ بررسی کنید `/api/` به Backend و سایر مسیرها به Next می‌روند، cookieها `Secure/HttpOnly` هستند، آپلود مستقیم از Nginx ممکن نیست، و rate limit مسیرهای حساس پاسخ مناسب می‌دهد. زمان، نسخه و نتیجهٔ health/readiness را در گزارش انتشار ثبت کنید.

## بازگشت و بازیابی

- اگر Migration اجرا نشده یا با کد قبلی سازگار است، فقط symlink را به release قبلی برگردانید و سرویس‌ها را restart و health check کنید. `alembic downgrade` را فقط برای Migration صراحتاً برگشت‌پذیر و بدون اتلاف داده به کار ببرید.
- برای آزمون بازیابی، `deploy/restore-test.sh /absolute/backup-directory` را با نقش دارای `CREATEDB` و libpq env امن اجرا کنید. اسکریپت پایگاه تازه با نام `hashti_restore_*` و پوشهٔ موقت جدید می‌سازد، dump و uploads را بازیابی می‌کند، checksum، تعداد رکوردها، تطبیق دفتر/مانده، وجود کیف پول برای همهٔ مخاطبان و وجود فایل‌های رسید/پوستر ارجاع‌شده را بررسی می‌کند. پایگاه و پوشهٔ موقت را برای بررسی دستی نگه می‌دارد؛ پس از ثبت نتیجه، اپراتور فقط همان هدف‌های دقیق را پاک کند. هرگز روی production restore آزمایشی اجرا نکنید.
- restore روی production فقط پس از تصمیم مسئول انتشار، توقف نوشتن، بررسی نسخهٔ بکاپ و برنامهٔ جلوگیری از از‌دست‌رفتن داده انجام شود؛ برای رفع صرفِ خطای کد، restore دیتابیس نکنید.

برای بستن H28 هنوز دسترسی سرور/دامنه، build موفق در محیط انتشار، health check روی همان محیط و یک restore واقعی با نتیجهٔ ثبت‌شده لازم است.
