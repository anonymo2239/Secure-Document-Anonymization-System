from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.core.mail import send_mail

import os
import struct
import json
import base64
import re
import io

import fitz  # PyMuPDF
import spacy
from PIL import Image, ImageFilter
from Cryptodome.Cipher import AES

from .models import UserEditor, Messages, EditorReferee  # Model bağlantıları


def mainpage(request):
    return render(request, 'mainpage.html')

def referee(request):
    """Hakemin atanmış makalelerini listele"""
    email = request.GET.get("email", "").strip()

    if email:
        documents = EditorReferee.objects.filter(referee_email=email)
    else:
        documents = None

    return render(request, "referee.html", {"documents": documents})


def assign_referee(request, article_id):
    """Admin tarafından hakeme makale atama işlemi."""
    article = get_object_or_404(UserEditor, id=article_id)

    if request.method == "POST":
        referee_email = request.POST.get("referee_email")

        if referee_email:
            # Hakeme makale atama işlemi
            EditorReferee.objects.create(
                referee_email=referee_email,
                anonymized_article=article.raw_article,  # PDF'yi sakla
            )
            return redirect("projectApp:adminpage")  # Admin sayfasına geri dön

    return JsonResponse({"error": "E-posta girilmedi."}, status=400)


def refereeassessment(request, article_id):
    """Hakemin değerlendirme yazacağı sayfa"""
    article = get_object_or_404(EditorReferee, id=article_id)  # EditorReferee tablosundan al

    if request.method == "POST":
        assessment_text = request.POST.get("assessment", "").strip().encode("utf-8")
        explanation_text = request.POST.get("explanation", "").strip()
        final_assessment_text = request.POST.get("final_assessment_article", "").strip().encode("utf-8")  # Formdaki isimle eşleşmeli!

        # Değerleri uygun formatta kaydet
        article.assessment = assessment_text if assessment_text else None
        article.explanation = explanation_text if explanation_text else None
        article.final_assessment_article = final_assessment_text if final_assessment_text else None

        article.save()
        return redirect("projectApp:referee")  # Değerlendirme tamamlandığında yönlendir

    return render(request, "refereeassessment.html", {"article": article})

def admin(request):
    """Admin panelini aç ve makaleleri listele."""
    articles = UserEditor.objects.all()
    return render(request, 'admin.html', {"articles": articles})



def generate_tracking_number():
    """AES kullanarak 7 basamaklı benzersiz bir takip numarası üretir."""
    random_data = os.urandom(16)  # Rastgele 16 bayt veri üret
    cipher = AES.new(b'S3cr3tAESKey1234', AES.MODE_ECB)  # Sabit AES anahtarı
    encrypted_data = cipher.encrypt(random_data)  # Rastgele veriyi AES ile şifrele

    # Şifrelenmiş ilk 8 baytı alıp tam sayıya çeviriyoruz
    numeric_value = struct.unpack("Q", encrypted_data[:8])[0]

    # 7 basamaklı bir takip numarası elde etmek için mod işlemi
    return str(numeric_value % 9000000 + 1000000)  # 1000000-9999999 arası sayı üret



@csrf_exempt
def uploadarticle(request):
    """Makale yükleme işlemi: PDF dosyasını kaydeder, AES ile takip numarası üretir ve e-posta gönderir."""
    
    if request.method == "GET":
        return render(request, 'uploadarticle.html')  # GET isteği için sayfayı döndür

    if request.method == "POST":
        email = request.POST.get("email")  # Kullanıcının e-posta adresini al
        pdf_file = request.FILES.get("file")  # Kullanıcının yüklediği PDF dosyasını al

        # Gerekli alanlar boş mu?
        if not email or not pdf_file:
            return JsonResponse({"error": "Lütfen e-posta adresinizi girin ve bir PDF yükleyin."}, status=400)

        # AES ile benzersiz takip numarası oluştur
        tracking_number = generate_tracking_number()

        # PDF dosyasını binary olarak oku
        pdf_binary_data = pdf_file.read()

        try:
            # Veritabanına kaydet
            user_article = UserEditor(
                tracking_no=tracking_number,
                owner_email=email,
                raw_article=pdf_binary_data
            )
            user_article.save()

            # Kullanıcıya takip numarasını içeren e-posta gönder
            send_mail(
                "Makale Takip Numaranız",
                f"Merhaba,\n\nMakaleniz başarıyla sisteme yüklendi.\nTakip numaranız: {tracking_number}\n\nBu numarayı kullanarak makalenizin durumunu sorgulayabilirsiniz.",
                "omer2020084@gmail.com",  # Burada kendi SMTP e-posta adresini kullan
                [email],
                fail_silently=False,
            )


            return JsonResponse({
                "success": "Makale başarıyla yüklendi.",
                "tracking_no": tracking_number
            })

        except Exception as e:
            return JsonResponse({"error": f"Bir hata oluştu: {str(e)}"}, status=500)

    return JsonResponse({"error": "Geçersiz istek."}, status=400)


@csrf_exempt
def send_message(request):
    if request.method == "POST":
        data = json.loads(request.body)
        sender = data.get("sender")  # Mesajı gönderen (admin veya kullanıcı email)
        receiver = data.get("receiver")  # Mesajın alıcısı (admin veya kullanıcı email)
        message = data.get("message")

        if not sender or not receiver or not message:
            return JsonResponse({"error": "Gönderen, alıcı ve mesaj gereklidir."}, status=400)

        Messages.objects.create(sender=sender, receiver=receiver, message=message)
        return JsonResponse({"success": "Mesaj başarıyla kaydedildi."})

    return JsonResponse({"error": "Geçersiz istek."}, status=400)


def get_messages(request):
    user_email = request.GET.get("email")  # Kullanıcının email'i

    if not user_email:
        return JsonResponse({"error": "E-posta adresi gerekli!"}, status=400)

    # Kullanıcının dahil olduğu (gönderdiği veya aldığı) tüm mesajları çekiyoruz
    messages = Messages.objects.filter(sender=user_email) | Messages.objects.filter(receiver=user_email)
    messages = messages.order_by("id")

    messages_list = [{"sender": msg.sender, "receiver": msg.receiver, "message": msg.message} for msg in messages]

    return JsonResponse(messages_list, safe=False)


def get_referee_documents(request):
    email = request.GET.get("email", "").strip()
    
    if not email:
        return JsonResponse([], safe=False)

    documents = UserEditor.objects.filter(referee_email=email)
    documents_list = [
        {"id": doc.id, "owner_email": doc.owner_email, "pdf_path": doc.raw_article.name}
        for doc in documents
    ]
    
    return JsonResponse(documents_list, safe=False)

@csrf_exempt
def check_article_status(request):
    """Takip numarasına göre makalenin durumunu sorgular."""
    if request.method == "POST":
        data = json.loads(request.body)
        tracking_no = data.get("tracking_no")

        if not tracking_no:
            return JsonResponse({"error": "Takip numarası gereklidir."}, status=400)

        try:
            article = UserEditor.objects.get(tracking_no=tracking_no)
            return JsonResponse({
                "tracking_no": article.tracking_no,
                "owner_email": article.owner_email,
                "status": "İnceleniyor"  # İlerleyen süreçlerde durumu güncelleyebilirsin.
            })
        except UserEditor.DoesNotExist:
            return JsonResponse({"error": "Geçersiz takip numarası."}, status=404)

    return JsonResponse({"error": "Geçersiz istek."}, status=400)

def queryarticle(request):
    """Makale sorgulama sayfasını açar."""
    return render(request, 'queryarticle.html')



# alperenin fonklar

def extract_author_info(text):
    """
    Makaledeki yazar isimlerini ve kurum bilgilerini bulan fonksiyon.
    """
    author_names = []
    institutions = []
    emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
    
    nlp = spacy.load("en_core_web_sm")
    doc = nlp(text)
    
    exclude_terms = {"Database", "IEEE", "System", "Model", "Analysis", "Emotion Recognition Using Temporally Localized",
            "Emotional Events in EEG With Naturalistic Context", 
            "An Efficient Approach to EEG-Based Emotion Recognition using LSTM Network"}
    
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            author_names.append(ent.text)
        elif ent.label_ in ["ORG", "GPE"] and ent.text not in exclude_terms:
            institutions.append(ent.text)
    
    return set(author_names), set(emails), set(institutions)

def anonymize_pdf(article):
    """
    PDF'den metni çıkar, sadece yazar isimlerini ve kurum bilgilerini sansürler ve yeni anonimleştirilmiş PDF oluşturur.
    """
    doc = fitz.open(stream=article.raw_article, filetype="pdf")
    total_pages = len(doc)

    target_pages = list(range(1)) + list(range(total_pages - 2, total_pages))
    
    text = "".join([doc[page].get_text("text") for page in target_pages])

    author_names, emails, institutions = extract_author_info(text)
    
    # Manuel olarak sansürlenmesi gereken isimleri ekleyelim
    manual_names_to_blur = {"MAJITHIA TEJAS VINODBHAI", "Kumar", "Hazarika", "Liu", "Atkinson", "Acharya", "Tripathi", "Sharma", "Bhattacharya", "Anubhav", "Debarshi",
                             "Takahashi", "Grandjean", "Nath"}
    author_names.update(manual_names_to_blur)
    
    # Sansürlenmemesi gereken başlıklar
    exclude_titles = [
        "Emotion Recognition Using Temporally Localized Emotional Events in EEG With Naturalistic Context: DENS# Dataset",
        "EEG signal processing and emotion recognition using Convolutional Neural Network",
        "An Efficient Approach to EEG-Based Emotion Recognition using LSTM Network"
    ]
    
    for page_num in target_pages:
        page = doc[page_num]
        page_text = page.get_text("text")
        page_lines = page_text.lower().split("\n")  # Tüm satırları al
        
        # Sayfadaki metnin herhangi bir yerinde başlıklar var mı kontrol et
        if any(title.lower() in page_text.lower() for title in exclude_titles):
            continue  

        # Sansürlenecek kelimeler
        words_to_blur = set(author_names) | set(emails) | set(institutions)

        for word in words_to_blur:
            if any(word.lower() in title.lower() for title in exclude_titles):
                continue  # Eğer kelime başlığın içinde geçiyorsa sansürleme
            
            text_instances = page.search_for(word)
            blurred_text = " " * len(word)
            for inst in text_instances:
                rect = fitz.Rect(inst.x0, inst.y0, inst.x1, inst.y1)
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                page.insert_textbox(rect, blurred_text, fontsize=12, color=(0, 0, 0), align=fitz.TEXT_ALIGN_CENTER)

    pdf_bytes = io.BytesIO()
    doc.save(pdf_bytes)
    pdf_bytes.seek(0)
    return pdf_bytes.read()


def anonymize_article(request, article_id):
    """
    Makale PDF'yi anonimleştirir, anonimleştirilmiş sürümü döndürür.
    """
    article = get_object_or_404(UserEditor, id=article_id)
    
    if not article.raw_article:
        return JsonResponse({"error": "Orijinal PDF bulunamadı."}, status=404)
    
    anonymized_pdf = anonymize_pdf(article)
    
    return HttpResponse(anonymized_pdf, content_type="application/pdf", headers={
        "Content-Disposition": 'inline; filename="anonim_makale.pdf"'
    })

def save_anonymized_article(request, article_id):
    """
    Anonimleştirilmiş PDF'yi veritabanına kaydeder.
    """
    article = get_object_or_404(UserEditor, id=article_id)
    
    if not article.raw_article:
        return JsonResponse({"error": "Orijinal PDF bulunamadı."}, status=404)
    
    anonymized_pdf = anonymize_pdf(article)
    
    editor_referee = EditorReferee.objects.create(
        referee_email=article.referee_email if article.referee_email else "example@domain.com",
        anonymized_article=anonymized_pdf
    )
    editor_referee.save()
    
    return JsonResponse({"message": "Anonimleştirilmiş PDF başarıyla kaydedildi."})

def deanonymize_article(request, article_id):
    """
    Orijinal PDF'yi döndürür.
    """
    article = get_object_or_404(UserEditor, id=article_id)
    
    if not article.raw_article:
        return JsonResponse({"error": "Orijinal PDF bulunamadı."}, status=404)
    
    return HttpResponse(article.raw_article, content_type="application/pdf", headers={
        "Content-Disposition": 'inline; filename="orijinal_makale.pdf"'
    })



def inspect_article(request, article_id):
    article = get_object_or_404(UserEditor, id=article_id)
    pdf_url = f"/view_article/{article.id}/"
    return render(request, "inspectarticle.html", {"pdf_url": pdf_url, "article_id": article_id})

def view_article_pdf(request, article_id):
    article = get_object_or_404(UserEditor, id=article_id)
    if article.raw_article:
        return HttpResponse(article.raw_article, content_type="application/pdf", headers={
            "Content-Disposition": 'inline; filename="makale.pdf"'
        })
    return JsonResponse({"error": "PDF bulunamadı."}, status=404)

