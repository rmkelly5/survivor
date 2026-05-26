from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import ChatMessage


@login_required
def chat_view(request):
    messages = list(ChatMessage.objects.select_related('author').order_by('-created_at', '-id')[:200])
    messages.reverse()
    if request.method == 'POST':
        body = (request.POST.get('body') or '').strip()
        if not body:
            return render(request, 'chat.html', {
                'messages': messages,
                'error': 'Message cannot be empty.',
            })
        ChatMessage.objects.create(
            author=request.user,
            body=body,
            message_type=ChatMessage.MESSAGE_USER,
        )
        return redirect('chat')

    return render(request, 'chat.html', {'messages': messages})


@login_required
def chat_poll_api(request):
    after_id = request.GET.get('after')
    qs = ChatMessage.objects.select_related('author').order_by('created_at', 'id')
    if after_id and str(after_id).isdigit():
        qs = qs.filter(id__gt=int(after_id))
    else:
        qs = qs.order_by('-created_at', '-id')[:200]
        qs = sorted(qs, key=lambda msg: (msg.created_at, msg.id))
    payload = [
        {
            'id': msg.id,
            'author': msg.author.username if msg.author else 'Survivor Bot',
            'body': msg.body,
            'message_type': msg.message_type,
            'week': msg.week,
            'created_at': msg.created_at.strftime('%b %d, %I:%M %p'),
            'is_system': msg.message_type == ChatMessage.MESSAGE_WEEKLY_LOCK,
        }
        for msg in qs
    ]
    return JsonResponse({'messages': payload})


@login_required
@require_POST
def chat_send_api(request):
    body = (request.POST.get('body') or '').strip()
    if not body:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)
    if len(body) > 2000:
        return JsonResponse({'error': 'Message is too long.'}, status=400)

    msg = ChatMessage.objects.create(
        author=request.user,
        body=body,
        message_type=ChatMessage.MESSAGE_USER,
    )
    return JsonResponse({
        'message': {
            'id': msg.id,
            'author': request.user.username,
            'body': msg.body,
            'message_type': msg.message_type,
            'week': msg.week,
            'created_at': msg.created_at.strftime('%b %d, %I:%M %p'),
            'is_system': False,
        }
    })
