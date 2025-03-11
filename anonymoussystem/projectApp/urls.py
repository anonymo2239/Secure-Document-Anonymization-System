from django.urls import path
from . import views

app_name = 'projectApp'

urlpatterns = [
    path('', views.mainpage, name='home'),
    path('referee/', views.referee, name='referee'),
    path('admin/', views.admin, name='adminpage'),
    path('uploadarticle/', views.uploadarticle, name='uploadarticle'),
    path('queryarticle/', views.queryarticle, name='queryarticle'),

]
