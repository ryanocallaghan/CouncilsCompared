"""Fetches the official figures behind councilscompared.com.

Each module in pipeline.sources fetches one publication and returns its
figures keyed by ONS code. pipeline.update runs them all and writes
data/sources/*.json and data/councils.json, which the site is built from.
"""
