from specialists.billing import billing
from specialists.counselling import counselling
from specialists.lifecycle import lifecycle
from specialists.refund import refund
from specialists.technical import technical

SPECIALISTS = [refund, technical, billing, counselling, lifecycle]

REGISTRY = {specialist.name: specialist for specialist in SPECIALISTS}
