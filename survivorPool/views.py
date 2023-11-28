from django.shortcuts import render
from django.http import HttpResponse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from . models import Pick
from django.urls import reverse_lazy
from .forms import PostForm

# Create your views here.
#def index(request):
    #return HttpResponse("Hello, world. You're at the Survivor Pool index.")

class HomeView(ListView):
    model = Pick
    template_name = 'home.html'
    ordering = ['week']

class AddPickView(CreateView):
    model = Pick
    form_class = PostForm
    template_name = 'add_pick.html'
    #fields = ['team', 'user_name', 'week']

class PickDetailView(DetailView):
    model = Pick
    template_name = 'pick_details.html'

class UpdatePickView(UpdateView):
    model = Pick
    template_name = 'update_pick.html'
    fields = ['team']

class DeletePickView(DeleteView):
    model = Pick
    template_name = 'delete_pick.html'
    fields = ['week']
    success_url = reverse_lazy('home')