import dateutil.parser
from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import generic

from .base import CanMonitorRaceMixin, UserMixin
from .. import forms, models


class Race(UserMixin, generic.DetailView):
    slug_url_kwarg = 'race'
    model = models.Race

    def get_chat_form(self):
        return forms.ChatForm()

    def get_invite_form(self):
        return forms.InviteForm()

    def get_context_data(self, **kwargs):
        race = self.get_object()
        return {
            **super().get_context_data(**kwargs),
            'chat_form': self.get_chat_form(),
            'available_actions': race.available_actions(self.user),
			'can_moderate': race.category.can_moderate(self.user),
            'can_monitor': race.can_monitor(self.user),
            'invite_form': self.get_invite_form(),
            'meta_image': self.request.build_absolute_uri(race.category.image.url) if race.category.image else None,
        }

    def get_queryset(self):
        category_slug = self.kwargs.get('category')
        queryset = super().get_queryset()
        queryset = queryset.filter(
            category__slug=category_slug,
        )
        return queryset


class RaceData(Race):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        resp = HttpResponse(
            content=self.object.json_data,
            content_type='application/json',
        )
        resp['X-Date-Exact'] = timezone.now().isoformat()
        return resp


class RaceRenders(Race):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.user.is_authenticated:
            resp = JsonResponse(
                self.object.get_renders(self.user, self.request)
            )
        else:
            resp = HttpResponse(
                content=self.object.json_renders,
                content_type='application/json',
            )
        resp['X-Date-Exact'] = timezone.now().isoformat()
        return resp


class RaceChat(Race):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        end = timezone.now()
        messages = self.object.message_set.filter(
            posted_at__lte=end,
        ).order_by('-posted_at')

        since = request.GET.get('since')
        if since:
            try:
                start = dateutil.parser.parse(since)
                messages = messages.filter(
                    posted_at__gt=start,
                )
            except (ValueError, OverflowError):
                return HttpResponseBadRequest(
                    'Unable to parse given timestamp in "since" parameter.'
                )
        else:
            start = None

        can_see_deleted = self.object.can_monitor(request.user)
        if not can_see_deleted:
            messages = messages.filter(deleted=False)

        return JsonResponse({
            'messages': [
                {
                    'id': message.hashid,
                    'user': (
                        message.user.api_dict_summary(race=self.object)
                        if not message.user.is_system else None
                    ),
                    'posted_at': message.posted_at,
                    'message': message.message,
                    'highlight': message.highlight,
                    'is_system': message.user.is_system,
                    **({
                        'deleted': message.deleted,
                        'deleted_by': str(message.deleted_by),
                    } if can_see_deleted else {}),
                }
                for message in reversed(messages.all()[:100])
            ],
            'start': start,
            'end': end,
            'tick_rate': self.object.tick_rate,
        })


class RaceFormMixin:
    def get_category(self):
        category_slug = self.kwargs.get('category')
        return get_object_or_404(models.Category.objects, slug=category_slug)

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            'category': self.get_category(),
        }


    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['category'] = self.get_category()
        kwargs['can_moderate'] = kwargs['category'].can_moderate(self.user)
        return kwargs


class CreateRace(UserPassesTestMixin, UserMixin, RaceFormMixin, generic.CreateView):
    form_class = forms.RaceCreationForm
    model = models.Race

    def form_valid(self, form):
        category = self.get_category()

        if not self.user.is_staff and self.user.opened_races.exclude(
            state__in=[
                models.RaceStates.finished.value,
                models.RaceStates.cancelled.value,
            ],
        ).exists():
            form.add_error(None, 'You can only have one open race room at a time.')
            return self.form_invalid(form)

        race = form.save(commit=False)

        race.category = category
        race.slug = category.generate_race_slug()

        if form.cleaned_data.get('invitational'):
            race.state = models.RaceStates.invitational.value

        race.opened_by = self.user

        race.save()

        return HttpResponseRedirect(race.get_absolute_url())

    def test_func(self):
        if not self.user.is_authenticated:
            return False
        return self.get_category().can_start_race(self.user)


class EditRace(CanMonitorRaceMixin, UserMixin, RaceFormMixin, generic.UpdateView):
    form_class = forms.RaceEditForm
    model = models.Race
    slug_url_kwarg = 'race'

    def test_func(self):
        return super().test_func() and self.get_object().is_preparing

    def form_valid(self, form):
        race = form.save()

        if 'goal' in form.changed_data or 'custom_goal' in form.changed_data:
            race.add_message(
                '%(user)s set a new goal: %(goal)s.'
                % {'user': self.user, 'goal': race.goal_str}
            )
        if 'info' in form.changed_data:
            race.add_message(
                '%(user)s updated the race information.'
                % {'user': self.user}
            )
        if 'streaming_required' in form.changed_data:
            if race.streaming_required:
                race.add_message('Streaming is now required for this race.')
            else:
                race.add_message('Streaming is now NOT required for this race.')

        return HttpResponseRedirect(race.get_absolute_url())
