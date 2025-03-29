**Database ekleme**

DATABASES = {
    'default':{
        'ENGINE':'mssql',                    # Must be "mssql"
        'NAME':'DbAnonymo',                       
        'HOST':'localhost\\SQLEXPRESS', # <server>\<instance>
        'PORT':'',                           # Keep it blank
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
        },
    }
}

* pip install mssql-django
* Sonra python manage.py inspectdb > models.py çalıştır.
* python manage.py makemigrations
* python manage.py migrate
* models.py dosyasını UTF-8 formatında kaydet

Ornek Degerlendirme:
EEG tabanli duygusal tanima icin yenilikci bir veri seti sunuyor. Yontem saglam ancak veri toplama sureci ve model detaylari yetersiz. Genellestirme calismalari ile katki artirilabilir.
