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
                            "text": "Pro sdílení dokumentů připojte k tomuto Prostoru SharePoint úložiště.",
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
                    "text": "Schválená bezpečnostní politika této aplikace vyžaduje, aby "
                },
                {
                    "type": "TextRun",
                    "text": "soubory kromě obrázků byly ukládány pouze do propojené složky Microsoft365 SharePoint Online. ",
                    "weight": "bolder"
                },
                {
                    "type": "TextRun",
                    "text": "Tlačítko \"Návod\" vás přesměruje na dokument, který popisuje, jak SharePoint Online k Prostoru připojit."
                }
            ]
        },
        {
            "type": "RichTextBlock",
            "inlines": [
                {
                    "type": "TextRun",
                    "text": "Vámi vložené soubory byly vymazány.",
                    "weight": "bolder"
                }
            ]
        },
        {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "Návod",
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
                            "text": "Pro sdílení dokumentů zkontrolujte, že je k tomuto Prostoru připojeno SharePoint úložiště.",
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
                    "text": "Schválená bezpečnostní politika této aplikace vyžaduje, aby "
                },
                {
                    "type": "TextRun",
                    "text": "soubory kromě obrázků byly ukládány pouze do propojené složky Microsoft365 SharePoint Online. ",
                    "weight": "bolder"
                },
                {
                    "type": "TextRun",
                    "text": "Tlačítko \"Návod\" vás přesměruje na dokument, který popisuje, jak SharePoint Online k Prostoru připojit."
                }
            ]
        },
        {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "Návod",
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
                            "text": "Uživatel {{display_name}} ({{email}}) nemá v IDM České pošty evidovanou identitu nebo chybí účet v ActiveDirectory.",
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
            "text": "Zajistěte registraci účtu dle standardního procesu a pak teprve přidejte uživatele do Týmu. Tlačítko \"Návod\" vás přesměruje na dokument, který popisuje, jak zajistit registraci identity nebo přidělit roli pro přístup do ActiveDirectory.",
            "wrap": True
        },
        {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "Návod",
                    "url": "{{url_idm_guide}}"
                },
                {
                    "type": "Action.OpenUrl",
                    "title": "Přejít do IDM",
                    "url": "{{url_idm}}"
                }
            ],
            "horizontalAlignment": "Right"
        }
    ]
}
