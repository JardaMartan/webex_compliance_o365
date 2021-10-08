from unidecode import unidecode

# form = bc.nested_replace_dict(bc.localize(bc.USER_WARNING_FORM, options["language"]), {"display_name": display_name, "email": event.data.personEmail, "group_name": team_info.name, "url_idm": os.getenv("URL_IDM"), "url_idm_guide": os.getenv("URL_IDM_GUIDE")})

# language list which is presented in settings
LANGUAGES = {
    "cs_CZ": "Čeština",
    "en_US": "English"
}

def lang_list_for_card():
    lan_list = []
    for (key, value) in LANGUAGES.items():
        lan_list.append({"title": value, "value": key})
        
    lan_list.sort(key=lambda x: unidecode(x["title"]).lower())
    
    return lan_list

# each language has to have its own constant here
CS_CZ = {
    "loc_default_form_msg": "Toto je formulář. Zobrazíte si ho v aplikaci nebo webovém klientovi Webex.",
    "spl_1": "Pro sdílení dokumentů připojte k tomuto Prostoru SharePoint Online úložiště.",
    "spl_2": "Schválená bezpečnostní politika této aplikace vyžaduje, aby ",
    "spl_3": "soubory kromě obrázků byly ukládány pouze do propojené složky Microsoft365 SharePoint Online. ",
    "spl_4": "Tlačítko \"Návod\" vás přesměruje na dokument, který popisuje, jak SharePoint Online k Prostoru připojit.",
    "spl_5": "Vámi vložené soubory byly vymazány.",
    "spw_1": "Pro sdílení dokumentů zkontrolujte, že je k tomuto Prostoru připojeno SharePoint Online úložiště.",
    "usr_1": "Uživatel {{display_name}} ({{email}}) byl odebrán z Týmu, protože nemá v IDM České pošty evidovanou identitu nebo chybí jeho účet v ActiveDirectory.",
    "usr_2": "Zajistěte registraci identity dle standardního procesu a pak teprve přidejte uživatele do Týmu. Tlačítko \"Návod\" vás přesměruje na dokument, který popisuje, jak zajistit registraci identity nebo přidělit roli pro přístup do ActiveDirectory.",
    "button_guide": "Návod",
    "button_idm": "Přejít do IDM"
}

EN_US = {
    "loc_default_form_msg": "This is a form. It can be displayed in a Webex app or web client.",
    "spl_1": "For document sharing, connect a SharePoint Online site and folder to this Space.",
    "spl_2": "Our security policy requires ",
    "spl_3": "files except images to be stored only to a connected folder on Microsoft365 SharePoint Online. ",
    "spl_4": "\"Guide\" button will display a document which describes how to connect SharePoint Online to the Space.",
    "spl_5": "Posted files have been deleted.",
    "spw_1": "For document sharing, verify that a SharePoint Online site and folder is connected to this Space.",
    "usr_1": "User {{display_name}} ({{email}}) has been removed from the Team. His/her identity could not be found or an account is missing in ActiveDirectory.",
    "usr_2": "Make sure the user has a standard or guest account and then add him/her to the Team. \"Guide\" button will display a document which describes how to register an identity or assign a role for ActiveDirectory access.",
    "button_guide": "Guide",
    "button_idm": "Go to IDM"
}

# add the  language constant to make it available for the Bot
LOCALES = {
    "cs_CZ": CS_CZ,
    "en_US": EN_US
}
