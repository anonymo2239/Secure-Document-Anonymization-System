from django.urls import path
from . import views

app_name = 'projectApp'

urlpatterns = [
    path('', views.mainpage, name='home'),
    path('referee/', views.referee, name='referee'),
    path('uploadarticle/', views.uploadarticle, name='uploadarticle'),
    path('queryarticle/', views.queryarticle, name='queryarticle'),
    path('send_message/', views.send_message, name='send_message'),
    path('get_messages/', views.get_messages, name='get_messages'),
    path('get_referee_documents/', views.get_referee_documents, name='get_referee_documents'),
    path("assign_referee/<int:article_id>/", views.assign_referee, name="assign_referee"),
    path("refereeassessment/<int:article_id>/", views.refereeassessment, name="refereeassessment"),
    path('merge_and_protect_pdf/<int:article_id>/', views.merge_and_protect_pdf, name='merge_and_protect_pdf'),
    path('view_protected_pdf/<int:id>/', views.view_protected_pdf, name='view_protected_pdf'),
    path('save_to_database/<int:article_id>/', views.save_to_database, name='save_to_database'),
    path('view_encrypted_pdf/<int:article_id>/', views.view_encrypted_pdf, name='view_encrypted_pdf'),

    path('admin/', views.admin, name='adminpage'),
    path('inspect_article/<int:id>/', views.inspect_article, name='inspect_article'),
    path('view_article/<int:article_id>/', views.view_article_pdf, name='view_article_pdf'),  # Hakem için
    path('view_article_admin/<int:id>/', views.view_article_admin, name='view_article_admin'),
    path('anonymize_article/<int:id>/', views.anonymize_article, name='anonymize_article'),
    path('deanonymize_article/<int:id>/', views.deanonymize_article, name='deanonymize_article'),
    path('check_article_status/', views.check_article_status, name='check_article_status'),
    path('admin/logrecords', views.logrecords, name='logrecords'),
    path('keyword_analysis/<int:id>/', views.keyword_analysis, name='keyword_analysis'),
    path('get_referees/', views.get_referees, name='get_referees'),
    path('view_final_assessment_pdf/<str:tracking_no>/', views.view_final_assessment_pdf, name='view_final_assessment_pdf'),

]