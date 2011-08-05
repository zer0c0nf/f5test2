from .base import SeleniumCommand
from ...interfaces.config import ConfigInterface, DeviceAccess
from ...interfaces.selenium import By, Is # ActionChains
from ...interfaces.selenium.driver import NoSuchElementException
from ...base import AttrDict
import os
import logging

LOG = logging.getLogger(__name__) 


class BannerError(Exception):
    pass

wait_for_loading = None
class WaitForLoading(SeleniumCommand):
    """Waits for the Loading XUI banner to change.

    @param timeout: Wait this many seconds for the task to finish (default: 60).
    @type timeout:  int
    @param interval: Polling interval (default: 1)
    @type interval:  int
    """
    def __init__(self, timeout=60, interval=1, css=None, *args, **kwargs):
        super(WaitForLoading, self).__init__(*args, **kwargs)
        self.timeout = timeout
        self.interval = interval
        self.css = css

    def setup(self):
        params = AttrDict()
        b = self.api

        def is_loading(e, exc):
            if e is None:
                # The banner should always be there, if we can't find it it's
                # probably because the page is loading. In this case we can't
                # decide whether it is done loading.
                return False
            is_visible = e.is_displayed()
            css = e.get_attribute('class')
            if not self.css is None:
                if css and 'loading' not in css:
                    return True
            else:
                if not is_visible or (css and 'loading' not in css):
                    return True
            return False

        params.value = '//div[@id="banner"]/div[@id="message"]/div[@id="messagetype"]'
        params.it = Is.TEST
        params.by = By.XPATH
        params.frame = None
        params.test = is_loading

        prev_frame = b._current_frame
        b.wait(timeout=self.timeout, interval=self.interval, **params)
        css = get_banner_css(ifc=self.ifc)
        b.switch_to_frame(prev_frame)
        if self.css and self.css not in css:
            raise BannerError("Unexpected banner! (css=%s)" % css)


get_banner_css = None
class GetBannerCss(SeleniumCommand):
    """Returns the banner type: success, warning, confirm, loading, etc..
    
    @return: A set of css class strings.
    @rtype: set
    """
    def setup(self):
        xpath = '//div[@id="message"]/div[@id="messagetype"]'

        b = self.api
        frame = b._current_frame
        if frame != None:
            b.switch_to_default_content()

        e = b.find_element_by_xpath(xpath)
        css_class = e.get_attribute('class').split()

        if frame != None:
            b.switch_to_frame(frame)
        
        return set(css_class)


get_cell_xpath = None
class GetCellXpath(SeleniumCommand):
    """Xpath builder for BS3-like tables.
    
    @param table_id: The ID of the table HTML element.
    @type table_id: str
    @param column: The column name as listed in the table header row.
    @type table_id: str
    @param value: The cell value to look for.
    @type value: str
    @param sortable: Is this column sortable?
    @type sortable: bool
    
    @return: The xpath
    @rtype: str
    """
    def __init__(self, table_id, column, value, sortable=True, *args, **kwargs):
        super(GetCellXpath, self).__init__(*args, **kwargs)
        self.table_id = table_id
        self.column = column
        self.value = value
        self.sortable = sortable

    def setup(self):
        b = self.api
        params = AttrDict()
        params.table_id = self.table_id
        # Validate the existence of the table with the required ID.

        params.column = self.column
        params.value = self.value
        if self.sortable:
            params.column_index = "count(//table[@id='%(table_id)s']/thead//*[contains(text(), '%(column)s')]/../preceding-sibling::*) + 1" % params
        else:
            params.column_index = "count(//table[@id='%(table_id)s']/thead//*[contains(text(), '%(column)s')]/preceding-sibling::*) + 1" % params
        xpath = "//table[@id='%(table_id)s']/tbody/tr[td[%(column_index)s]//self::*[contains(text(), '%(value)s')]]" % params
        #b.find_element_by_xpath("//table[@id='%(table_id)s']" % params)
        try:
            b.find_element_by_xpath(xpath)
            return xpath
        except NoSuchElementException:
            LOG.debug('Cell with value %(value)s not found in table %(table_id)s on column %(column)s.' % params)


login = None
class Login(SeleniumCommand):
    """Log in command.
    
    @param device: The device.
    @type device: str or DeviceAccess instance
    @param address: The IP or hostname.
    @type address: str
    @param username: The username.
    @type username: str
    @param password: The password.
    @type password: str
    """
    def __init__(self, device=None,
                 address=None, username=None, password=None, timeout=120, 
                 *args, **kwargs):
        super(Login, self).__init__(*args, **kwargs)
        self.timeout = timeout
        if device or not address:
            self.device = device if isinstance(device, DeviceAccess) \
                        else ConfigInterface().get_device(device)
            self.address = address or self.device.address
            self.username = username or self.device.get_admin_creds().username
            self.password = password or self.device.get_admin_creds().password
        else:
            self.device = device
            self.address = address
            self.username = username
            self.password = password

    def setup(self):
        b = self.api
        # Set the api login data
        ret = AttrDict(device=self.device, address=self.address,
                       username=self.username, password=self.password)
        self.ifc._set_credentials(ret)

        b.get("https://%s/tmui/login.jsp" % self.address).wait('username', 
                                                               timeout=self.timeout)
        
        e = b.find_element_by_name("username")
        e.click()
        e.send_keys(self.username)
        
        e = b.find_element_by_id("passwd")
        e.send_keys(self.password)
        #e.submit().wait('mainmenu-overview')
        #e.submit().wait('mainmenu-overview-welcome')
        #e.submit().wait('status')
        e.submit().wait('#trail > a', by=By.CSS_SELECTOR, timeout=20)
        b.maximize_window()

        # XXX: DISABLE XUI menus hover behavior. This should stay here until
        #      Selenium2 implements the advanced user interactions for all 
        #      browsers
        #b.execute_script("$('#mainpanel li').unbind('mouseenter mouseleave');")

        return ret


screen_shot = None
class ScreenShot(SeleniumCommand):
    """Take a screenshot and save the page source.
    
    @param dir: Output directory (must have write permissions).
    @type dir: str
    @param screenshot: the name of the screenshot file (default: screenshot).
    @type screenshot: str
    """
    def __init__(self, dir, name='screenshot', *args, **kwargs):
        super(ScreenShot, self).__init__(*args, **kwargs)
        self.dir = dir
        self.name = name
    
    def setup(self):
        b = self.api
        filename = os.path.join(self.dir, '%s.png' % self.name)
        if b.get_screenshot_as_file(filename):
            LOG.info('Screenshot dumped to: %s' % filename)

        try:
            filename = os.path.join(self.dir, '%s.html' % self.name)
            src = b.page_source
            src = src.replace('<HEAD>', '<HEAD><BASE href="%s"/>' % b.current_url)
            src = src.replace('/xui/common/scripts/api.js', '')
            with open(filename, "wt") as f:
                f.write(src.encode('utf-8'))
        except IOError, e:
            LOG.error('I/O error dumping source: %s', e)


logout = None
class Logout(SeleniumCommand):
    """Log out by clicking on the Logout button."""
    def setup(self):
        b = self.api
        e = b.find_element_by_id("logout")
        e.click().wait('username')
        self.ifc._del_credentials()


close_all_windows = None
class CloseAllWindows(SeleniumCommand):
    """Close all windows but the main."""
    def setup(self):
        b = self.api
        all_windows = b.window_handles or []
        if len(all_windows) <= 1:
            return
        main_window = self.ifc.window
        for window in all_windows:
            if window != main_window:
                b.switch_to_window(window)
                b.close()
        b.switch_to_window(main_window)


browse_to_tab = None
class BrowseToTab(SeleniumCommand):
    """XUI tab navigator. JQuery based.

    @param locator: Tab locator (e.g. Device | NTP)
    @type locator: str
    """
    def __init__(self, locator, *args, **kwargs):
        super(BrowseToTab, self).__init__(*args, **kwargs)
        self.locator = locator

    def setup(self):
        b = self.api
        LOG.info('Browsing to tab: %s', self.locator)
        b.switch_to_default_content()
        locator = self.locator

        if locator == 'Options':
            xpath = "//div[@id='pagemenu']//a[(not(@class) or " \
                    "@class != 'options') and text()='Options']"
        else:
            xpath = "//div[@id='pagemenu']"
            count = 0
            for t in locator.split('|'):
                count += 1
                t = t.strip()
                if t.startswith('[') and t.endswith(']'):
                    xpath += "/ul/li[%s]" % t[1:-1]
                else:
                    if count == 1:
                        xpath += "/ul/li[@class != 'options' and a[text()='%s']]" % t
                    else:
                        xpath += "/ul/li[a[text()='%s']]" % t
                if count == 1:
                    b.wait(xpath, by=By.XPATH)
                e = b.find_element_by_xpath(xpath)
                #e.click()
            
            # XXX: Uses direct JQuery calls.
            menu_id = e.get_attribute('id')
            b.execute_script("$('#%s a').click();" % menu_id)

            #xpath += '/a'
            #e = b.find_element_by_xpath(xpath)
            #e.click()
            

browse_to = None
class BrowseTo(SeleniumCommand):
    """XUI menu navigator. JQuery based.
    
    @param locator: Menu locator (e.g. System | Logs : Options)
    @type locator: str
    """
    def __init__(self, locator, *args, **kwargs):
        super(BrowseTo, self).__init__(*args, **kwargs)
        self.locator = locator

    def setup(self):
        b = self.api
        LOG.info('Browsing to: %s', self.locator)

        b.switch_to_default_content()
        bits = self.locator.split(':', 1)
        locator = bits[0]
        index = 1
        if locator.endswith('[+]'):
            locator = locator.replace('[+]', '', 1).rstrip()
            index = 2

        panel, locator = locator.split('|', 1)
        panel = panel.strip()
        locator = locator.strip()
        xpath = "//div[@id='mainpanel']/div[a[text()='%s']]" % panel
        e = b.find_element_by_xpath(xpath)
        css = e.get_attribute('class').split()
        if 'open' not in css:
            e = b.find_element_by_xpath("%s/a" % xpath)
            e.click()
    
        for t in locator.split('|'):
            t = t.strip()
            if t.startswith('[') and t.endswith(']'):
                xpath += "/ul/li[%s]" % t[1:-1]
            else:
                xpath += "/ul/li[a='%s']" % t
            e = b.find_element_by_xpath(xpath)
        
        # XXX: Uses direct JQuery calls.
        menu_id = e.get_attribute('id')
        b.execute_script("$('#%s a:nth(%d)').click();" % (menu_id, index-1))

#        # Broken:
#        xpath += '/a[%d]' % index
#        e = b.find_element_by_xpath(xpath)
#        e.click()

        if len(bits) == 2:
            locator = bits[1]
            wait_for_loading(ifc=self.ifc)
            browse_to_tab(locator, ifc=self.ifc)

        elif len(bits) > 2:
            raise Exception('bad locator: %s Only one : allowed' % locator)


set_preferences = None
class SetPreferences(SeleniumCommand):
    """Sets the "Idle time before automatic logout" in System->Preferences.
    
    @param timeout: The idle timeout value.
    @type timeout: int
    """
    def __init__(self, prefs=None, *args, **kwargs):
        super(SetPreferences, self).__init__(*args, **kwargs)
        self.prefs = prefs

    def setup(self):
        b = self.api
        browse_to('System | Preferences', ifc=self.ifc)
        b.wait('div_security_table', frame='contentframe')
        b.switch_to_frame('contentframe')

        # Dirty flag
        anything = False
        
        if self.prefs.get('timeout'):
            e = b.find_element_by_name('gui_session_inactivity_timeout')
            value = e.get_attribute('value')
            new_value = self.prefs.timeout
            if int(value) != new_value:
                LOG.info('Setting preference timeout=%s', new_value)
                e.clear()
                e.send_keys(str(new_value))
                anything = True

        if self.prefs.get('records'):
            e = b.find_element_by_name('records_per_page')
            value = e.get_attribute('value')
            new_value = self.prefs.records
            if int(value) != new_value:
                LOG.info('Setting preference records=%s', new_value)
                e.clear()
                e.send_keys(str(new_value))
                anything = True

        if anything:
            e = b.find_element_by_id("update")
            e.click()
            wait_for_loading(ifc=self.ifc)


set_platform_configuration = None
class SetPlatformConfiguration(SeleniumCommand):
    """Sets the values in System->Platform page.
    
    @param values: Values to be updates.
    @type timeout: int
    """
    def __init__(self, values=None, *args, **kwargs):
        super(SetPlatformConfiguration, self).__init__(*args, **kwargs)
        self.values = values

    def setup(self):
        b = self.api
        browse_to('System | Platform', ifc=self.ifc)
        update = b.wait('platform_update', frame='contentframe')
        b.switch_to_frame('contentframe')

        # Dirty flag
        anything = False

        if not self.values.get('ssh') is None:
            enabled = self.values.get('ssh', False)
            access = b.find_element_by_id('service.ssh')
            if (enabled and not access.is_selected() or
                not enabled and access.is_selected()):
                if enabled:
                    LOG.info("Enabling SSH Access.")
                else:
                    LOG.info("Disabling SSH Access.")
                access.click()
                anything = True
            
        if anything:
            update.click()
            wait_for_loading(ifc=self.ifc)

delete_items = None
class DeleteItems(SeleniumCommand):
    """Deletes selected items in a table. Expects success banner.
    """
    def setup(self):
        b = self.api
        LOG.debug('Deleting selected items...')
        try:
            delete_button = b.find_element_by_xpath("//input[@value='Delete...']")
        except NoSuchElementException:
            delete_button = b.find_element_by_xpath("//input[@value='Delete']")
        delete_button = delete_button.click().wait("delete_confirm", By.NAME)
        delete_button.click()
        wait_for_loading(ifc=self.ifc)
        LOG.debug('Deleted successfully.')