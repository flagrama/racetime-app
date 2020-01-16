from django.db import models
from django.utils import timezone

from ..utils import get_hashids, SafeException


class Message(models.Model):
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
    )
    race = models.ForeignKey(
        'Race',
        on_delete=models.CASCADE,
    )
    posted_at = models.DateTimeField(
        auto_now_add=True,
    )
    message = models.TextField(
        max_length=1000,
    )
    highlight = models.BooleanField(
        default=False,
    )
    deleted = models.BooleanField(
        default=False,
    )
    deleted_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        related_name='+',
        null=True,
        default=None,
    )
    deleted_at = models.DateTimeField(
        null=True,
        default=None,
    )

    def delete_message(self, deleted_by):
        """
        Delete the message.
        """
        if self.deleted:
            raise SafeException(
                'Cannot delete a message that is already deleted.'
            )

        self.deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by_id = deleted_by.id
        self.save()

    @property
    def hashid(self):
        return get_hashids(self.__class__).encode(self.id)
