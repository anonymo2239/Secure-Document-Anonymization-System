# Article Anonymization Website with Django

This project is an independent article anonymization platform developed to enhance impartiality in academic evaluation processes. Users can upload their manuscripts to the system, where editors assign them to appropriate referees. Referees evaluate only anonymized versions of the articles, free from any identifying elements such as author names, contact details, affiliations, or facial visuals.

Throughout the process, personal information is kept confidential, ensuring a fair and unbiased review.

## Features

- **Article Upload and Anonymization**
  - Users can upload their manuscripts in PDF format.
  - Author names, emails, affiliations, and facial visuals are automatically censored using NLP and image processing tools.

- **Editor Dashboard**
  - Editors can review uploaded articles, assign referees, and oversee the review process.

- **Referee Evaluation System**
  - Referees evaluate only anonymized content, ensuring an impartial review process.

- **Feedback Workflow**
  - Editor receives the referee's evaluation and forwards it to the article owner.

- **Confidentiality and Fairness**
  - AES encryption secures all sensitive data.
  - Identity information is masked to provide a fully anonymous evaluation.

## Technologies Used

- **Backend:** Python, Django  
- **Database:** MS SQL Server  
- **IDE:** Visual Studio  
- **PDF Processing:** PyMuPDF (`fitz`), PyPDF2, pdf2image, FPDF  
- **Image Processing:** OpenCV  
- **NLP:** spaCy, NLTK, TF-IDF via Scikit-learn  
- **Encryption:** PyCryptodome (AES)

## NLP and Anonymization Pipeline

- **Named Entity Recognition:** spaCy is used to extract personal names, emails, and affiliations.
- **Face Blurring:** Haar Cascade classifier (OpenCV) is used to detect and blur facial content within PDFs.
- **Keyword Extraction:** TF-IDF is used to extract relevant keywords for potential referee matching.

## Installation & Usage

### Requirements

- Python 3.1+
- Django 4.x
- MS SQL Server
- Visual Studio
- ODBC Driver for SQL Server

### Setup Instructions

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/Django-Anonymized-Article-System.git
   ```

2. Create a database on MS SQL Server:
   ```sql
   CREATE DATABASE DbAnonymo;
   ```

3. Update the connection string in `settings.py` to match your SQL Server configuration.

4. Open the project in Visual Studio.

5. Run the project:
   ```bash
   python manage.py runserver
   ```

6. Run migrations to initialize the database:
   ```bash
   python manage.py migrate
   ```

## Security & Encryption

- All uploaded articles are encrypted using AES before storage.
- Tracking numbers are generated using AES-based randomness.
- Final PDFs can be encrypted and locked from editing after evaluation.

## Contact

To contribute or report an issue, please use the repository or contact:  
`alperen.arda.adem22@gmail.com`  
`omer2020084@gmail.com`

### Photos

![](images/image1.png)
*He/she can access the relevant pages via the buttons here for article upload, inquiry, referee and editorial operations.*

![](images/image2.png)
*Users can upload their articles from this field to the system and start the evaluation process.*

![](images/image3.png)
*The user can see the stage of his/her article in the evaluation process and review the feedback from the referee.*

![](images/image4.png)
*Referees can view the anonymized articles assigned to them in this field and enter their evaluation notes into the system.*

![](images/image5.png)
*'Suggest me recipe' page that we can see the situation of recipes*

![](images/image6.png)
*The editor can review the uploaded articles, appoint referees and manage the evaluation process.*
