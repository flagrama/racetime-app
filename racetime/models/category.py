import json
from functools import partial

from django.conf import settings
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.transaction import atomic
from django.urls import reverse
from django.utils import timezone

from .choices import RaceStates
from ..utils import SafeException, generate_race_slug


class Category(models.Model):
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text='The full name of this category, e.g. "Super Mario 64".',
    )
    short_name = models.CharField(
        max_length=16,
        unique=True,
        help_text='An abbreviation or other short identifier, e.g. "SM64".',
    )
    slug = models.CharField(
        max_length=255,
        unique=True,
        help_text=(
            'A unique identifier for this category used in the URL, '
            'e.g. "tetris-99".'
        ),
    )
    image = models.ImageField(
        null=True,
        blank=True,
        help_text='Recommended size: 285x380. No larger than 100kb.',
    )
    info = models.TextField(
        null=True,
        blank=True,
        help_text=(
            'Displayed on the category page. Limited use of HTML is allowed.'
        ),
    )
    streaming_required = models.BooleanField(
        default=True,
        help_text=(
            'Require entrants to be streaming when they join a race. '
            'Moderators may override this for individual races.'
        ),
    )
    active = models.BooleanField(
        default=True,
        help_text='Allow new races to be created in this category.'
    )
    owner = models.ForeignKey(
        'User',
        on_delete=models.PROTECT,
        help_text='The user who controls this category.',
    )
    moderators = models.ManyToManyField(
        'User',
        related_name='mod_categories',
        help_text='Users who can moderate races in this category.',
        blank=True,
    )
    slug_words = models.TextField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            'Set a number of words to be picked at random for race room '
            'names. If set, you must provide a minimum of 100 distinct words '
            'to use. Changing slug words will not impact existing race rooms.'
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    @property
    def json_data(self):
        """
        Return current race data as a JSON string.
        """
        return cache.get_or_set(
            self.slug + '/data',
            self.dump_json_data,
            settings.RT_CACHE_TIMEOUT,
        )

    @property
    def moderator_list(self):
        """
        Return a comma-separated string listing all moderators.
        """
        return ', '.join(str(user) for user in self.moderators.all())

    def api_dict_summary(self):
        return {
            'name': self.name,
            'short_name': self.short_name,
            'slug': self.slug,
            'url': self.get_absolute_url(),
            'data_url': self.get_data_url(),
        }

    def can_edit(self, user):
        return user.is_active and (user.is_superuser or user == self.owner)

    def can_moderate(self, user):
        """
        Determine if the given user can moderate this category.
        """
        return user.is_active and (
            user.is_superuser
            or user == self.owner
            or user in self.moderators.all()
        )

    def can_start_race(self, user):
        return self.active and user.is_active and not user.is_banned_from_category(self)

    def dump_json_data(self):
        value = json.dumps({
            **self.api_dict_summary(),
            'image': self.image.url if self.image else None,
            'info': self.info,
            'streaming_required': self.streaming_required,
            'owner': self.owner.api_dict_summary(category=self),
            'moderators': [user.api_dict_summary(category=self) for user in self.moderators.all()],
            'current_races': [
                {
                    'name': str(race),
                    'status': {
                        'value': race.state_info.value,
                        'verbose_value': race.state_info.verbose_value,
                        'help_text': race.state_info.help_text,
                    },
                    'url': race.get_absolute_url(),
                    'data_url': race.get_data_url(),
                    'goal': {
                        'name': race.goal_str,
                        'custom': not race.goal,
                    },
                    'entrants_count': race.entrants_count,
                    'entrants_count_inactive': race.entrants_count_inactive,
                    'opened_at': race.opened_at,
                    'started_at': race.started_at,
                    'time_limit': race.time_limit,
                }
                for race in self.race_set.exclude(state__in=[
                    RaceStates.finished,
                    RaceStates.cancelled,
                ]).all()
            ],
        }, cls=DjangoJSONEncoder)

        cache.set(str(self) + '/data', value, None)
        return value

    def get_absolute_url(self):
        return reverse('category', args=(self.slug,))

    def get_data_url(self):
        return reverse('category_data', args=(self.slug,))

    def generate_race_slug(self):
        """
        Generate an unused, unique race slug for races in this category.
        """
        if self.slug_words:
            generator = partial(generate_race_slug, self.slug_words.split('\n'))
        else:
            generator = generate_race_slug

        slug = generator()
        attempts_left = 99
        while self.race_set.filter(slug=slug).exists() and attempts_left > 0:
            slug = generator()
            attempts_left -= 1

        if attempts_left == 0:
            raise SafeException(
                'Cannot generate a distinct race slug. There may not be '
                'enough slug words available.'
            )

        return slug

    def __str__(self):
        return self.name


class CategoryRequest(models.Model):
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text='The full name of this category, e.g. "Super Mario 64".',
    )
    short_name = models.CharField(
        max_length=16,
        unique=True,
        help_text='An abbreviation or other short identifier, e.g. "SM64".',
    )
    slug = models.CharField(
        max_length=255,
        unique=True,
        help_text=(
            'A unique identifier for this category used in the URL, '
            'e.g. "tetris-99".'
        ),
    )
    goals = models.TextField(
        help_text='One goal per line. A category must have at least one goal.',
    )
    requested_at = models.DateTimeField(
        auto_now_add=True,
    )
    requested_by = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
    )
    reviewed_at = models.DateTimeField(
        null=True,
    )
    accepted_as = models.ForeignKey(
        'Category',
        on_delete=models.CASCADE,
        null=True,
    )

    @atomic
    def accept(self):
        category = Category.objects.create(
            name=self.name,
            short_name=self.short_name,
            slug=self.slug,
            owner=self.requested_by,
        )
        for goal in set(self.goals.split('\n')):
            category.goal_set.create(name=goal)

        self.reviewed_at = timezone.now()
        self.accepted_as = category
        self.save()

    def reject(self):
        self.reviewed_at = timezone.now()
        self.save()


class Goal(models.Model):
    category = models.ForeignKey(
        'Category',
        on_delete=models.CASCADE,
    )
    name = models.CharField(
        max_length=255,
        help_text='The win conditions for the race, e.g. "16 stars".',
    )
    description = models.TextField(
        null=True,
        blank=True,
        max_length=2000,
        help_text=(
            'Any additional information or rules that apply to this race goal.'
        ),
    )
    active = models.BooleanField(
        default=True,
        help_text='Allow new races to be created with this goal.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['category', 'name'],
                name='unique_category_name',
            ),
        ]

    def __str__(self):
        return self.name
