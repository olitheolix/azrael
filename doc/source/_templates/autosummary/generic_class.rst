Class: {{ fullname }}
======={{ underline }}

.. currentmodule:: {{ module }}

{% block methods %}

{% if methods %}
.. rubric:: Methods

.. autosummary::
{% for item in methods %}
   ~{{ name }}.{{ item }}
{%- endfor %}
{% endif %}
{% endblock %}

{% block attributes %}
{% if attributes %}
.. rubric:: Attributes

.. autosummary::
{% for item in attributes %}
   ~{{ name }}.{{ item }}
{%- endfor %}
{% endif %}
{% endblock %}

Class Documentation
===================

.. autoclass:: {{ objname }}
   :members:

