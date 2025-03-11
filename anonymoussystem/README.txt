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

* Sonra python manage.py inspectdb > models.py çalıştır.
* python manage.py makemigrations
* python manage.py migrate
* models.py dosyasını UTF-8 formatında kaydet
