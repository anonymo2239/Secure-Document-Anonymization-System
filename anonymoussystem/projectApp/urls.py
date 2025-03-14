from django.urls import path
from . import views

app_name = 'projectApp'

urlpatterns = [
    path('', views.mainpage, name='home'),
    # omerin url ler
    path('referee/', views.referee, name='referee'),
    path('uploadarticle/', views.uploadarticle, name='uploadarticle'),
    path('queryarticle/', views.queryarticle, name='queryarticle'),
    path('send_message/', views.send_message, name='send_message'),
    path('get_messages/', views.get_messages, name='get_messages'),
    path('get_referee_documents/', views.get_referee_documents, name='get_referee_documents'),

    # alperenin url ler
    path('admin/', views.admin, name='adminpage'),
    path('inspect_article/<int:article_id>/', views.inspect_article, name='inspect_article'),
    path('view_article/<int:article_id>/', views.view_article_pdf, name='view_article_pdf'),
    path('deanonymize_article/<int:article_id>/', views.deanonymize_article, name='deanonymize_article'),


]
