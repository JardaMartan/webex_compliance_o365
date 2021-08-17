def wrap_form(form):
    card = EMPTY_CARD
    card["content"] = form
    
    return card

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
                            "text": "Pro sdílení MS Office dokumentů připojte k tomuto Prostoru SharePoint úložiště.",
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
            "text": "MS Office dokumenty podléhají klasifikaci a musí být proto uloženy na SharePointu. Tlačítko Návod vás přesměruje na dokument, který popisuje, jak SharePoint k Prostoru připojit.",
            "wrap": True
        },
        {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "Návod",
                    "url": "https://help.webex.com/cs-cz/n4ve41eb/Webex-Link-a-Microsoft-OneDrive-or-SharePoint-Online-Folder-to-a-Space"
                }
            ],
            "horizontalAlignment": "Right"
        }
    ]
}
