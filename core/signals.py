"""Milestone -> calendar-push wiring (plan §7c writes).

A signal rather than overriding Milestone.save() (unlike Task.save()'s
existing recurring-task hook in models.py) because this one makes a real
network call -- that must never block or crash an admin save. push.py's
own functions already catch and log every provider failure internally, so
a save always succeeds locally regardless of what happens on the wire."""

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from core.calendarsync import push
from core.models import Milestone


@receiver(post_save, sender=Milestone)
def _push_milestone_on_save(sender, instance, **kwargs):
    push.push_milestone(instance)


@receiver(pre_delete, sender=Milestone)
def _remove_milestone_push_on_delete(sender, instance, **kwargs):
    push.remove_milestone_push(instance)
