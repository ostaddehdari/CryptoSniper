"""Human-readable connection guidance. Never contains user credentials."""

SUPPORTED_CONNECTION_GUIDES = {
    "bitunix": {"name":"Bitunix","credential_fields":["API Key","API Secret"],"steps":[
        "در Bitunix وارد API Management شوید و یک API Key جدید بسازید.",
        "مجوز خواندن حساب و Spot Trading را فعال کنید.",
        "مجوز Withdrawal/برداشت را فعال نکنید.",
        "در صورت امکان IP سرور CryptoSniper را در IP Whitelist ثبت کنید.",
        "API Key و API Secret را در CryptoSniper وارد و بررسی اتصال را اجرا کنید."
    ]},
    "lbank": {"name":"LBank","credential_fields":["API Key","API Secret"],"steps":[
        "در Security / API Management یک کلید API جدید ایجاد کنید.",
        "Read و Spot Trading را فعال و Withdrawal را غیرفعال نگه دارید.",
        "IP ثابت سرور را در محدودیت IP کلید ثبت کنید.",
        "Key و Secret را در CryptoSniper ذخیره و تست اتصال را اجرا کنید."
    ]},
    "nobitex": {"name":"Nobitex","credential_fields":["API Token"],"steps":[
        "در حساب نوبیتکس از بخش تنظیمات/API یک Token اختصاصی ایجاد کنید.",
        "Token را فقط با دسترسی‌های لازم برای خواندن حساب و معامله ایجاد کنید.",
        "در صورت وجود کنترل برداشت یا IP، برداشت را غیرفعال و IP سرور را محدود کنید.",
        "Token را در فیلد API Key وارد کنید؛ Secret برای Adapter نوبیتکس لازم نیست."
    ]},
    "weex": {"name":"WEEX","credential_fields":["API Key","API Secret","Passphrase"],"steps":[
        "در WEEX به API Management بروید و کلید تازه بسازید.",
        "Read و Spot Trading را فعال کنید و Withdrawal را غیرفعال بگذارید.",
        "Passphrase ساخته‌شده برای API را نگه دارید و IP سرور را Whitelist کنید.",
        "Key، Secret و Passphrase را در CryptoSniper وارد و بررسی اتصال را اجرا کنید."
    ]},
    "ourbit": {"name":"Ourbit","credential_fields":["API Key","API Secret"],"steps":[
        "در Ourbit از API Management یک API Key جدید ایجاد کنید.",
        "فقط Read و مجوز معامله لازم را فعال کنید؛ مجوز برداشت نباید فعال باشد.",
        "در صورت پشتیبانی، IP سرور را روی کلید محدود کنید.",
        "Key و Secret را در CryptoSniper وارد و بررسی اتصال را اجرا کنید."
    ]},
}
