from django.shortcuts import render

def mainpage(request):
    return render(request, 'mainpage.html')

def referee(request):
    return render(request, 'referee.html')

def admin(request):
    return render(request, 'admin.html')


def uploadarticle(request):
    return render(request, 'uploadarticle.html')



def queryarticle(request):
    return render(request, 'queryarticle.html')
