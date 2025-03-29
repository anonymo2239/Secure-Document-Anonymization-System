from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib import messages

import cv2
import numpy as np
from pdf2image import convert_from_path
from fpdf import FPDF

import os
import struct
import json
import re
import io

import fitz  # PyMuPDF
import spacy
from PIL import Image
from Cryptodome.Cipher import AES
from Cryptodome.Random import get_random_bytes
import base64

from .models import UserEditor, Messages, EditorReferee, Logs, Messages, Referees  # Model bağlantıları

from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PIL import Image, ImageDraw, ImageFont
import tempfile
from nltk.corpus import stopwords
import string
from sklearn.feature_extraction.text import TfidfVectorizer

AES_KEY = b'S3cr3tAESKey1234'

def encrypt_binary_data(data, key):
    """AES ile binary veriyi şifreler."""
    cipher = AES.new(key, AES.MODE_EAX)
    ciphertext, tag = cipher.encrypt_and_digest(data)
    return base64.b64encode(cipher.nonce + tag + ciphertext)

def decrypt_binary_data(data, key):
    """AES ile binary veriyi çözer."""
    data = base64.b64decode(data)
    nonce = data[:16]
    tag = data[16:32]
    ciphertext = data[32:]
    cipher = AES.new(key, AES.MODE_EAX, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag)

def mainpage(request):
    return render(request, 'mainpage.html')

def admin(request):
    """Admin panelini aç ve makaleleri listele."""
    articles = UserEditor.objects.all()

    # Her makale için düzenlenmiş PDF olup olmadığını kontrol et
    for article in articles:
        # Hakem değerlendirmesi var mı kontrolü
        referee_entry = EditorReferee.objects.filter(article_id=article.id).first()
        if referee_entry and referee_entry.final_assessment_article:
            article.has_final_assessment = True
        else:
            article.has_final_assessment = False

    return render(request, 'admin.html', {"articles": articles})



def logrecords(request):
    """Log kayıtlarını listele."""
    logs = Logs.objects.all().order_by('-log_date')  # En yeni kayıtlar en üstte
    return render(request, 'logrecords.html', {"logs": logs})

def referee(request):
    """Hakemin atanmış makalelerini listele"""
    email = request.GET.get("email", "").strip()

    if email:
        documents = EditorReferee.objects.filter(referee_email=email)
    else:
        documents = None

    return render(request, "referee.html", {"documents": documents})

def assign_referee(request, article_id):
    """
    Admin tarafından hakeme makale atama işlemi.
    """
    # Orijinal makaleyi UserEditor tablosundan al
    article = get_object_or_404(UserEditor, id=article_id)
    data = json.loads(request.body)
    referee_email = data.get("referee_email")

    # Makale sahibinin e-posta adresini al
    article_owner = article.owner_email

    # Makalenin daha önce yönlendirilip yönlendirilmediğini kontrol et
    existing_assignment = EditorReferee.objects.filter(article_id=article_id).first()
    if existing_assignment:
        return JsonResponse({"message": "Bu makale zaten bir hakeme yönlendirilmiştir."})

    # PDF'yi anonimleştir (blurlama işlemi)
    anonymized_pdf = anonymize_pdf(article, blur_names=True, blur_emails=True, blur_institutions=True)

    # Anonimleştirilmiş PDF'i AES ile şifrele
    encrypted_pdf = encrypt_binary_data(anonymized_pdf, AES_KEY)

    # Anonimleştirilmiş ve şifrelenmiş PDF'yi EditorReferee tablosuna kaydet
    try:
        editor_referee = EditorReferee.objects.create(
            article_id=article_id,
            anonymized_article=encrypted_pdf,
            referee_email=referee_email
        )
        editor_referee.save()
    except Exception as e:
        return JsonResponse({"message": f"Hakeme yönlendirme başarısız: {str(e)}"})

    # Log kaydı oluştur
    log_message = f"{article_owner} kullanıcısının makalesi {timezone.now().strftime('%d-%m-%Y %H:%M:%S')} tarihinde hakeme iletildi."
    try:
        log = Logs(log_date=timezone.now(), log_details=log_message)
        log.save()
    except Exception as e:
        return JsonResponse({"message": f"Log kaydı başarısız: {str(e)}"})

    return JsonResponse({"message": "Hakeme yönlendirme başarıyla yapıldı."})



def refereeassessment(request, article_id):
    """
    Hakemin değerlendirme yazacağı sayfa
    """
    article = get_object_or_404(EditorReferee, id=article_id)

    if request.method == "POST":
        explanation_text = request.POST.get("explanation", "").strip()
        if explanation_text:
            article.explanation = explanation_text
            article.save()
        return redirect("projectApp:referee")

    return render(request, "refereeassessment.html", {"article": article})


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

        if not email or not pdf_file:
            return JsonResponse({"error": "Lütfen e-posta adresinizi girin ve bir PDF yükleyin."}, status=400)
        tracking_number = generate_tracking_number()
        pdf_binary_data = pdf_file.read()

        try:
            user_article = UserEditor(
                tracking_no=tracking_number,
                owner_email=email,
                raw_article=pdf_binary_data
            )
            user_article.save()

            log_message = f"{email} kullanıcısının makalesi {timezone.now().strftime('%d-%m-%Y %H:%M:%S')} tarihinde editöre ulaştı."
            log = Logs(log_date=timezone.now(), log_details=log_message)
            log.save()

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
    if request.method == "POST":
        data = json.loads(request.body)
        tracking_no = data.get("tracking_no")

        if not tracking_no:
            return JsonResponse({"error": "Takip numarası gereklidir."}, status=400)

        try:
            article = UserEditor.objects.get(tracking_no=tracking_no)
            logs = Logs.objects.filter(log_details__icontains=article.owner_email)
            log_list = [log.log_details for log in logs]

            referee_entry = EditorReferee.objects.filter(article_id=article.id).first()
            has_final_assessment = bool(referee_entry and referee_entry.final_assessment_article)

            return JsonResponse({
                "tracking_no": article.tracking_no,
                "owner_email": article.owner_email,
                "status": "İnceleniyor",
                "logs": log_list,
                "has_final_assessment": has_final_assessment
            })
        except UserEditor.DoesNotExist:
            return JsonResponse({"error": "Geçersiz takip numarası."}, status=404)

    return JsonResponse({"error": "Geçersiz istek."}, status=400)

def queryarticle(request):
    """Makale sorgulama sayfasını açar."""
    return render(request, 'queryarticle.html')


def view_article_pdf(request, article_id):
    article = get_object_or_404(EditorReferee, article_id=article_id)
    # has_final_assessment değerini burada belirliyoruz
    article.has_final_assessment = bool(article.final_assessment_article)

    if article.anonymized_article:
        return HttpResponse(article.anonymized_article, content_type="application/pdf", headers={
            "Content-Disposition": 'inline; filename="makale.pdf"'
        })
    return JsonResponse({"error": "PDF bulunamadı."}, status=404)

def view_final_assessment_pdf(request, tracking_no):
    try:
        # Öncelikle UserEditor tablosundan makaleyi bul
        user_article = UserEditor.objects.get(tracking_no=tracking_no)
        # Daha sonra EditorReferee tablosunda makalenin final değerlendirme PDF'sini bul
        article = EditorReferee.objects.get(article_id=user_article.id)
        if article.final_assessment_article:
            return HttpResponse(article.final_assessment_article, content_type="application/pdf")
        else:
            return HttpResponse("Final değerlendirme PDF'si bulunamadı.", status=404)
    except UserEditor.DoesNotExist:
        return HttpResponse("Makale bulunamadı.", status=404)
    except EditorReferee.DoesNotExist:
        return HttpResponse("Final değerlendirme PDF'si bulunamadı.", status=404)



def view_article_admin(request, id):
    article = get_object_or_404(UserEditor, id=id)
    if article.raw_article:
        return HttpResponse(article.raw_article, content_type="application/pdf", headers={
            "Content-Disposition": 'inline; filename="raw_makale.pdf"'
        })
    return JsonResponse({"error": "Makale bulunamadı."}, status=404)


def merge_and_protect_pdf(original_pdf_bytes, explanation_text):
    """
    PDF'yi bellek üzerinde birleştirir ve düzenlenemez hale getirir.
    Hakem değerlendirmesini görüntü olarak PDF'e ekler.
    """
    try:
        # PDF Birleştirme
        merger = PdfMerger()
        original_pdf = BytesIO(original_pdf_bytes)
        merger.append(original_pdf)

        # Değerlendirme Metnini Görüntüye Dönüştürme
        img = Image.new('RGB', (595, 842), color=(255, 255, 255))  # A4 boyutunda beyaz sayfa
        draw = ImageDraw.Draw(img)
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        try:
            font = ImageFont.truetype(font_path, 20)
        except IOError:
            font = ImageFont.load_default()

        # Metni satırlara böl ve ekle
        y_position = 50
        max_line_length = 80
        lines = [explanation_text[i:i + max_line_length] for i in range(0, len(explanation_text), max_line_length)]
        for line in lines:
            draw.text((50, y_position), line, font=font, fill=(0, 0, 0))
            y_position += 30

        # Görüntüyü PDF'e dönüştür
        image_pdf = BytesIO()
        img.save(image_pdf, format="PDF")
        image_pdf.seek(0)

        # PDF'yi birleştirme
        merged_pdf = BytesIO()
        final_merger = PdfMerger()
        final_merger.append(original_pdf)  # Orijinal PDF'i birleştir
        final_merger.append(image_pdf)    # Görüntü PDF'ini birleştir
        final_merger.write(merged_pdf)
        final_merger.close()
        merged_pdf.seek(0)

        # Düzenlenemez PDF oluşturma
        protected_pdf = BytesIO()
        pdf_writer = PdfWriter()

        reader = PdfReader(merged_pdf)
        for page in reader.pages:
            pdf_writer.add_page(page)

        # PDF'nin düzenlenemez hale getirilmesi
        pdf_writer.encrypt(user_password="", owner_password="ownerpassword", use_128bit=True)

        pdf_writer.write(protected_pdf)
        protected_pdf.seek(0)

        return merged_pdf.getvalue(), protected_pdf.getvalue()

    except Exception as e:
        print(f"[ERROR] PDF oluşturulurken hata: {str(e)}")
        return None, None


def save_to_database(request, article_id):
    """
    Birleştirilmiş ve şifrelenmiş PDF'yi veritabanına kaydeder.
    """
    if request.method == 'POST':
        explanation_text = request.POST.get('explanation', '')

        # Veritabanından orijinal makale PDF'sini alırken article_id'yi kullanıyoruz
        try:
            referee_article = get_object_or_404(EditorReferee, article_id=article_id)
            user_article = get_object_or_404(UserEditor, id=article_id)
        except Exception as e:
            print(f"[ERROR] Makale bulunamadı: {str(e)}")
            return JsonResponse({"error": f"Makale bulunamadı: {str(e)}"}, status=404)

        # Makale sahibinin e-posta adresini al
        article_owner_email = user_article.owner_email

        original_pdf_bytes = user_article.raw_article  # Orijinal (anonimleştirilmemiş) PDF
        anonymized_pdf_bytes = referee_article.anonymized_article  # Anonimleştirilmiş PDF

        # PDF oluşturma ve şifreleme (orijinal ve değerlendirme birleştirilmiş PDF)
        merged_pdf, final_assessment_pdf = merge_and_protect_pdf(original_pdf_bytes, explanation_text)

        # Veriyi kaydet
        if final_assessment_pdf:
            referee_article.final_assessment_article = final_assessment_pdf
            referee_article.explanation = explanation_text
            referee_article.save()
            print(f"[SUCCESS] Veritabanına başarıyla kaydedildi. ID: {article_id}")

            # Log kaydı oluştur
            log_message = f"Hakem, {article_owner_email} kullanıcısının makalesine {timezone.now().strftime('%d-%m-%Y %H:%M:%S')} tarihinde cevap verdi."
            try:
                log = Logs(log_date=timezone.now(), log_details=log_message)
                log.save()
            except Exception as e:
                print(f"[ERROR] Log kaydı yapılamadı: {str(e)}")

        return redirect(f'/refereeassessment/{article_id}/')

    return JsonResponse({"error": "Geçersiz istek yöntemi."}, status=400)



def view_encrypted_pdf(request, article_id):
    """
    Şifrelenmiş PDF'yi yeni sekmede görüntüleme fonksiyonu.
    """
    try:
        article = get_object_or_404(EditorReferee, id=article_id)
        if article.final_assessment_article:
            # Şifrelenmiş veriyi çöz
            decrypted_pdf = decrypt_binary_data(article.final_assessment_article, AES_KEY)
            response = HttpResponse(decrypted_pdf, content_type="application/pdf")
            response['Content-Disposition'] = 'inline; filename="sifrelenmis_makale.pdf"'
            return response
        return JsonResponse({"error": "Şifrelenmiş PDF bulunamadı."}, status=404)
    except EditorReferee.DoesNotExist:
        return JsonResponse({"error": "Makale bulunamadı."}, status=404)
    except Exception as e:
        return JsonResponse({"error": f"Çözme işlemi başarısız: {str(e)}"}, status=500)



def view_protected_pdf(request, id):
    article = get_object_or_404(EditorReferee, id=id)
    # has_final_assessment alanını burada belirliyoruz
    article.has_final_assessment = bool(article.final_assessment_article)
    
    if article.has_final_assessment:
        return HttpResponse(article.final_assessment_article, content_type="application/pdf", headers={
            "Content-Disposition": 'inline; filename="duzenlenmis_makale.pdf"'
        })
    return HttpResponse("Düzenlenmiş PDF bulunamadı.", status=404)




# alperenin fonklar

def get_referees(request):
    try:
        referees = Referees.objects.all()
        referees_list = [
            {"referee_mail": referee.referee_mail, "referee_interests": referee.referee_interests}
            for referee in referees
        ]
        return JsonResponse(referees_list, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

# Haar Cascade modelini yükleme (yüz tespiti için)
face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
face_cascade = cv2.CascadeClassifier(face_cascade_path)

def blur_faces(image):
    """
    Yüzleri bulanıklaştırır.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    for (x, y, w, h) in faces:
        face_roi = image[y:y+h, x:x+w]
        blurred_face = cv2.GaussianBlur(face_roi, (99, 99), 30)
        image[y:y+h, x:x+w] = blurred_face
    return image

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


def anonymize_pdf(article, blur_names=False, blur_emails=False, blur_institutions=False):
    """
    PDF'den metni çıkar, yazar isimlerini, e-posta adreslerini, kurum bilgilerini ve yüzleri sansürler.
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
    
    words_to_blur = set()
    if blur_names:
        words_to_blur.update(author_names)
    if blur_emails:
        words_to_blur.update(emails)
    if blur_institutions:
        words_to_blur.update(institutions)

    # Sansürlenmemesi gereken başlıklar
    exclude_titles = [
        "Emotion Recognition Using Temporally Localized Emotional Events in EEG With Naturalistic Context: DENS# Dataset",
        "EEG signal processing and emotion recognition using Convolutional Neural Network",
        "An Efficient Approach to EEG-Based Emotion Recognition using LSTM Network"
    ]

    for page_num in range(total_pages):
        page = doc[page_num]
        page_text = page.get_text("text")

        # Başlık kontrolü
        if any(title.lower() in page_text.lower() for title in exclude_titles):
            continue

        # Yüzleri bulanıklaştırma işlemi
        pix = page.get_pixmap()
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img = np.array(img)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)  # OpenCV formatına dönüştür
        img = blur_faces(img)

        # Bulanıklaştırılmış resmi tekrar PDF sayfasına dönüştür
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img)
        img_bytes = io.BytesIO()
        pil_img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        # Sayfayı güncelle
        rect = fitz.Rect(0, 0, pix.width, pix.height)
        page.insert_image(rect, stream=img_bytes.getvalue())

        # Metinsel sansür işlemleri
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

@csrf_exempt
def anonymize_article(request, id):
    """
    Makale PDF'yi anonimleştirir, anonimleştirilmiş sürümü döndürür.
    """
    article = get_object_or_404(UserEditor, id=id)

    try:
        data = json.loads(request.body)
        print("Sunucuya Gelen Veriler:", data)  # VERİLERİ LOG YAZDIRMA

        blur_names = data.get("blur_names", False)
        blur_emails = data.get("blur_emails", False)
        blur_institutions = data.get("blur_institutions", False)

        print(f"İsimleri Gizle: {blur_names}, E-posta Gizle: {blur_emails}, Kurum Gizle: {blur_institutions}")

        anonymized_pdf = anonymize_pdf(article, blur_names, blur_emails, blur_institutions)

        return HttpResponse(anonymized_pdf, content_type="application/pdf", headers={
            "Content-Disposition": 'inline; filename="anonim_makale.pdf"'
        })
    except Exception as e:
        print("Anonimleştirme Hatası:", str(e))  # Hataları da logla
        return JsonResponse({"error": str(e)}, status=500)

def deanonymize_article(request, id):
    """
    Orijinal PDF'yi döndürür.
    """
    article = get_object_or_404(UserEditor, id=id)
    
    if not article.raw_article:
        return JsonResponse({"error": "Orijinal PDF bulunamadı."}, status=404)
    
    return HttpResponse(article.raw_article, content_type="application/pdf", headers={
        "Content-Disposition": 'inline; filename="orijinal_makale.pdf"'
    })


stop_words = set(stopwords.words('english'))

def extract_keywords(text):
    # Metni küçük harfe dönüştür
    text = text.lower()
    # Noktalama işaretlerini kaldır
    text = text.translate(str.maketrans('', '', string.punctuation))
    # Kelimeleri ayır
    words = text.split()
    # Anlamsız kelimeleri çıkar
    filtered_words = [word for word in words if word not in stop_words]
    cleaned_text = ' '.join(filtered_words)

    # TF-IDF kullanarak anlamlı kelime öbeklerini bul
    vectorizer = TfidfVectorizer(ngram_range=(1, 3), stop_words='english')
    tfidf_matrix = vectorizer.fit_transform([cleaned_text])
    feature_names = vectorizer.get_feature_names_out()
    tfidf_scores = tfidf_matrix.toarray()[0]

    # Skorları eşleştir ve en yüksek skorluları bul
    scored_keywords = list(zip(feature_names, tfidf_scores))
    sorted_keywords = sorted(scored_keywords, key=lambda x: x[1], reverse=True)
    top_keywords = [keyword for keyword, score in sorted_keywords[:6]]

    return top_keywords


def analyze_pdf_keywords(article):
    doc = fitz.open(stream=article.raw_article, filetype="pdf")
    total_pages = len(doc)
    target_pages = list(range(1)) + list(range(total_pages - 2, total_pages))
    text = "".join([doc[page].get_text("text") for page in target_pages])
    keywords = extract_keywords(text)
    return keywords


def keyword_analysis(request, id):
    article = get_object_or_404(UserEditor, id=id)
    try:
        keywords = analyze_pdf_keywords(article)

        # Hakem önerisi bulma
        referees = Referees.objects.all()
        best_match = None
        best_score = 0
        matched_referees = []

        for referee in referees:
            interests = set(referee.referee_interests.lower().split(", "))
            match_count = len(set(keywords).intersection(interests))
            matched_referees.append((referee, match_count))

        # Skorlara göre sırala (büyükten küçüğe)
        matched_referees.sort(key=lambda x: x[1], reverse=True)

        # JSON yanıtı oluştur
        referee_list = [{"referee_mail": ref[0].referee_mail, "referee_interests": ref[0].referee_interests} for ref in matched_referees]

        return JsonResponse({"keywords": keywords, "referees": referee_list})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def assign_referee(request, article_id):
    """
    Admin tarafından hakeme makale atama işlemi.
    """
    # Orijinal makaleyi UserEditor tablosundan al
    article = get_object_or_404(UserEditor, id=article_id)
    data = json.loads(request.body)
    referee_email = data.get("referee_email")

    # Makale sahibinin e-posta adresini al
    article_owner = article.owner_email

    # Makalenin daha önce yönlendirilip yönlendirilmediğini kontrol et
    existing_assignment = EditorReferee.objects.filter(article_id=article_id).first()
    if existing_assignment:
        return JsonResponse({"message": "Bu makale zaten bir hakeme yönlendirilmiştir."})

    # PDF'yi anonimleştir (blurlama işlemi)
    anonymized_pdf = anonymize_pdf(article, blur_names=True, blur_emails=True, blur_institutions=True)

    # Anonimleştirilmiş PDF'yi EditorReferee tablosuna kaydet
    try:
        editor_referee = EditorReferee.objects.create(
            article_id=article_id,
            anonymized_article=anonymized_pdf,
            referee_email=referee_email
        )
        editor_referee.save()
    except Exception as e:
        return JsonResponse({"message": f"Hakeme yönlendirme başarısız: {str(e)}"})

    # Log kaydı oluştur
    log_message = f"{article_owner} kullanıcısının makalesi {timezone.now().strftime('%d-%m-%Y %H:%M:%S')} tarihinde hakeme iletildi."
    try:
        log = Logs(log_date=timezone.now(), log_details=log_message)
        log.save()
    except Exception as e:
        return JsonResponse({"message": f"Log kaydı başarısız: {str(e)}"})

    return JsonResponse({"message": "Hakeme yönlendirme başarıyla yapıldı."})

def inspect_article(request, id):
    # Orijinal makaleyi UserEditor tablosundan al
    article = get_object_or_404(UserEditor, id=id)
    pdf_url = f"/view_article/{article.id}/"
    return render(request, "inspectarticle.html", {"pdf_url": pdf_url, "id": id})