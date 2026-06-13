from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .gmail_services import connect_mail, fetch_email_ids, read_email, save_email
from .models import GmailEmail


@require_GET
def sync_emails(request):
    try:
        mail = connect_mail()
        email_ids = fetch_email_ids(mail)

        existing_ids = set(GmailEmail.objects.values_list('gmail_id', flat=True))

        saved_count = 0
        skipped_count = 0

        for e_id in email_ids:
            data = read_email(mail, e_id)

            if data["gmail_id"] in existing_ids:
                skipped_count += 1
                continue

            created = save_email(data)
            if created:
                saved_count += 1

        # Breakdown by sender
        from django.db.models import Count
        breakdown = GmailEmail.objects.values('sender').annotate(total=Count('id')).order_by('-total')

        return JsonResponse({
            "status": "success",
            "total_in_gmail": len(email_ids),
            "saved_this_sync": saved_count,
            "skipped_duplicates": skipped_count,
            "total_in_db": GmailEmail.objects.count(),
            "breakdown_by_sender": list(breakdown)
        })

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
def list_emails(request):
    emails = GmailEmail.objects.all().order_by('-created_at').values(
        'gmail_id', 'sender', 'subject', 'body', 'created_at'
    )
    return JsonResponse({"status": "success", "emails": list(emails)})