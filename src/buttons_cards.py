import localization_strings as ls

def wrap_form(form):
    card = EMPTY_CARD
    card["content"] = form
    
    return card

def nested_replace(structure, original, new):
    """replace {{original}} wrapped strings with new value
    use recursion to walk the whole sructure
    
    arguments:
    structure -- input dict / list / string
    original -- string to search for
    new -- will replace every occurence of {{original}}
    """
    if type(structure) == list:
        return [nested_replace( item, original, new) for item in structure]

    if type(structure) == dict:
        return {key : nested_replace(value, original, new)
                     for key, value in structure.items() }

    if type(structure) == str:
        return structure.replace("{{"+original+"}}", str(new))
    else:
        return structure
        
def nested_replace_dict(structure, replace_dict):
    """replace multiple {{original}} wrapped strings with new value
    use recursion to walk the whole sructure
    
    arguments:
    structure -- input dict / list / string
    replace_dict -- dict where key matches the {{original}} and value provides the replacement
    """
    for (key, value) in replace_dict.items():
        structure = nested_replace(structure, key, value)
        
    return structure

# form = bc.nested_replace_dict(bc.localize(bc.USER_WARNING_FORM, options["language"]), {"display_name": display_name, "email": event.data.personEmail, "group_name": team_info.name, "url_idm": os.getenv("URL_IDM"), "url_idm_guide": os.getenv("URL_IDM_GUIDE")})
def localize(structure, language):
    """localize structure using {{original}} wrapped strings with new value
    use recursion to walk the whole sructure
    
    arguments:
    structure -- input dict / list / string
    language -- language code which is used to match key in ls.LOCALES dict
    """
    if not language in ls.LOCALES.keys():
        return structure
        
    lang_dict = ls.LOCALES[language]
    return nested_replace_dict(structure, lang_dict)

# wrapper structure for Webex attachments list        
EMPTY_CARD = {
    "contentType": "application/vnd.microsoft.card.adaptive",
    "content": None,
}

SP_LINK_FORM = {
    "type": "AdaptiveCard",
    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
    "version": "1.2",
    "body": [
        {
            "type": "ColumnSet",
            "columns": [
                {
                    "type": "Column",
                    "width": 20,
                    "items": [
                        {
                            "type": "Image",
                            "url": "https://cdn2.iconfinder.com/data/icons/color-svg-vector-icons-2/512/warning_alert_attention_search-512.png",
                            "size": "Small"
                        }
                    ]
                },
                {
                    "type": "Column",
                    "width": 80,
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "{{spl_1}}",
                            "wrap": True,
                            "weight": "Bolder",
                            "color": "Attention"
                        }
                    ]
                }
            ]
        },
        {
            "type": "RichTextBlock",
            "inlines": [
                {
                    "type": "TextRun",
                    "text": "{{spl_2}}"
                },
                {
                    "type": "TextRun",
                    "text": "{{spl_3}}",
                    "weight": "bolder"
                },
                {
                    "type": "TextRun",
                    "text": "{{spl_4}}"
                }
            ]
        },
        {
            "type": "RichTextBlock",
            "inlines": [
                {
                    "type": "TextRun",
                    "text": "{{spl_5}}",
                    "weight": "bolder"
                }
            ]
        },
        {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "{{button_guide}}",
                    "url": "{{url_onedrive_link}}"
                }
            ],
            "horizontalAlignment": "Right"
        }
    ]
}

SP_WARNING_FORM = {
    "type": "AdaptiveCard",
    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
    "version": "1.2",
    "body": [
        {
            "type": "ColumnSet",
            "columns": [
                {
                    "type": "Column",
                    "width": 20,
                    "items": [
                        {
                            "type": "Image",
                            "url": "https://cdn2.iconfinder.com/data/icons/color-svg-vector-icons-2/512/warning_alert_attention_search-512.png",
                            "size": "Small"
                        }
                    ]
                },
                {
                    "type": "Column",
                    "width": 80,
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "{{spw_1}}",
                            "wrap": True,
                            "weight": "Bolder",
                            "color": "Attention"
                        }
                    ]
                }
            ]
        },
        {
            "type": "RichTextBlock",
            "inlines": [
                {
                    "type": "TextRun",
                    "text": "{{spl_2}}"
                },
                {
                    "type": "TextRun",
                    "text": "{{spl_3}}",
                    "weight": "bolder"
                },
                {
                    "type": "TextRun",
                    "text": "{{spl_4}}"
                }
            ]
        },
        {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "{{button_guide}}",
                    "url": "{{url_onedrive_link}}"
                }
            ],
            "horizontalAlignment": "Right"
        }
    ]
}

USER_WARNING_FORM = {
    "type": "AdaptiveCard",
    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
    "version": "1.2",
    "body": [
        {
            "type": "ColumnSet",
            "columns": [
                {
                    "type": "Column",
                    "width": 20,
                    "items": [
                        {
                            "type": "Image",
                            "url": "https://cdn2.iconfinder.com/data/icons/color-svg-vector-icons-2/512/warning_alert_attention_search-512.png",
                            "size": "Small"
                        }
                    ]
                },
                {
                    "type": "Column",
                    "width": 80,
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "{{usr_1}}",
                            "wrap": True,
                            "weight": "Bolder",
                            "color": "Attention"
                        }
                    ]
                }
            ]
        },
        {
            "type": "TextBlock",
            "text": "{{usr_2}}",
            "wrap": True
        },
        {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "{{button_guide}}",
                    "url": "{{url_idm_guide}}"
                },
                # {
                #     "type": "Action.OpenUrl",
                #     "title": "{{button_idm}}",
                #     "url": "{{url_idm}}"
                # }
            ],
            "horizontalAlignment": "Right"
        }
    ]
}
