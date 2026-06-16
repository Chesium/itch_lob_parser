#!/usr/bin/env python3

"""Small printing helpers matching the original EperlUtil.pm behavior."""

from __future__ import annotations


def vprintl(*items: object) -> None:
    for item in items:
        print(item)


def vprinti(*items: object) -> None:
    for item in items:
        for line in str(item).splitlines():
            stripped = line.lstrip()
            if not stripped.startswith("|"):
                continue
            payload = stripped[1:]
            if payload.startswith(" "):
                payload = payload[1:]
            print(payload)
