from django.contrib import admin
from django.urls import path
from apps.gmail_integration.views import sync_emails

from apps.gmail_integration.views import list_emails

urlpatterns = [
    path('admin/', admin.site.urls),
    path("sync-emails/", sync_emails, name="sync_emails"),
    path("emails/", list_emails, name="list_emails"),

]