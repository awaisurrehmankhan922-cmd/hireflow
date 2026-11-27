<?php
/**
 * Plugin Name: HireFlow Connector
 * Description: Forwards existing application-form submissions to the HireFlow AI platform. Integration only:
 *              forms, pages and the WordPress database are left untouched. Submissions are queued locally,
 *              so applications are never lost while the AI platform is offline.
 * Version:     1.0.0
 * Requires PHP: 7.4
 */

if (!defined('ABSPATH')) exit;

final class HireFlow_Connector {
    const OPT = 'hireflow_connector';
    const CRON = 'hireflow_retry_queue';
    const MAX_ATTEMPTS = 50;

    public static function init() {
        register_activation_hook(__FILE__, [__CLASS__, 'activate']);
        register_deactivation_hook(__FILE__, [__CLASS__, 'deactivate']);
        add_filter('cron_schedules', [__CLASS__, 'schedules']);
        add_action(self::CRON, [__CLASS__, 'flush_queue']);
        add_action('admin_menu', [__CLASS__, 'menu']);
        add_action('admin_init', [__CLASS__, 'register_settings']);

        // Supported form plugins (enable whichever the site uses; others are ignored).
        add_action('wpcf7_before_send_mail', [__CLASS__, 'from_cf7']);                 // Contact Form 7
        add_action('wpforms_process_complete', [__CLASS__, 'from_wpforms'], 10, 4);     // WPForms
        add_action('gform_after_submission', [__CLASS__, 'from_gravity'], 10, 2);      // Gravity Forms
        add_action('hireflow_submit_application', [__CLASS__, 'enqueue'], 10, 1);     // custom forms: do_action(...)
    }

    /* ---------- lifecycle ---------- */
    public static function activate() {
        global $wpdb;
        require_once ABSPATH . 'wp-admin/includes/upgrade.php';
        // Own table, prefixed; no existing tables are altered.
        dbDelta("CREATE TABLE {$wpdb->prefix}hireflow_queue (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            payload LONGTEXT NOT NULL,
            attempts INT NOT NULL DEFAULT 0,
            last_error TEXT NULL,
            created_at DATETIME NOT NULL,
            sent_at DATETIME NULL,
            PRIMARY KEY (id), KEY sent_at (sent_at)
        ) {$wpdb->get_charset_collate()};");
        if (!wp_next_scheduled(self::CRON)) wp_schedule_event(time() + 60, 'hireflow_5min', self::CRON);
    }

    public static function deactivate() { wp_clear_scheduled_hook(self::CRON); }

    public static function schedules($s) {
        $s['hireflow_5min'] = ['interval' => 300, 'display' => 'Every 5 minutes (HireFlow)'];
        return $s;
    }

    /* ---------- form adapters ---------- */
    public static function from_cf7($form) {
        if (!self::form_enabled('cf7', $form->id())) return;
        $sub = WPCF7_Submission::get_instance();
        if (!$sub) return;
        self::enqueue(self::map('cf7', (string)$form->id(), (string)$sub->get_meta('timestamp') . '-' . wp_generate_uuid4(), $sub->get_posted_data()));
    }

    public static function from_wpforms($fields, $entry, $form_data, $entry_id) {
        if (!self::form_enabled('wpforms', $form_data['id'])) return;
        $flat = [];
        foreach ($fields as $f) $flat[sanitize_key($f['name'])] = $f['value'];
        self::enqueue(self::map('wpforms', (string)$form_data['id'], (string)$entry_id, $flat));
    }

    public static function from_gravity($entry, $form) {
        if (!self::form_enabled('gravity', $form['id'])) return;
        $flat = [];
        foreach ($form['fields'] as $f) $flat[sanitize_key($f->label)] = rgar($entry, (string)$f->id);
        self::enqueue(self::map('gravity', (string)$form['id'], (string)$entry['id'], $flat));
    }

    private static function form_enabled($plugin, $id) {
        $ids = array_filter(array_map('trim', explode(',', self::opt('form_ids', ''))));
        return empty($ids) || in_array("$plugin:$id", $ids, true) || in_array((string)$id, $ids, true);
    }

    /** Map arbitrary field names to the HireFlow contract using the configurable field map. */
    private static function map($plugin, $form_id, $entry_id, array $data) {
        $pick = function ($key, $default) use ($data) {
            foreach (array_map('trim', explode('|', self::opt("map_$key", $default))) as $name) {
                if (!empty($data[$name])) return is_array($data[$name]) ? implode(', ', $data[$name]) : (string)$data[$name];
            }
            return '';
        };
        return [
            'entry_id'  => $entry_id,
            'form_id'   => "$plugin-$form_id",
            'email'     => sanitize_email($pick('email', 'your-email|email|email_address')),
            'full_name' => sanitize_text_field($pick('name', 'your-name|name|full_name')),
            'phone'     => sanitize_text_field($pick('phone', 'your-phone|phone|mobile')),
            'position'  => sanitize_text_field($pick('position', 'position|job|vacancy')),
            'fields'    => array_map(function ($v) { return is_array($v) ? array_map('sanitize_text_field', $v) : sanitize_textarea_field((string)$v); }, $data),
        ];
    }

    /* ---------- queue + delivery ---------- */
    public static function enqueue(array $payload) {
        global $wpdb;
        $wpdb->insert("{$wpdb->prefix}hireflow_queue", ['payload' => wp_json_encode($payload), 'created_at' => current_time('mysql', true)]);
        self::deliver((int)$wpdb->insert_id); // best effort now; cron retries otherwise. Never blocks the form.
    }

    public static function flush_queue() {
        global $wpdb;
        $ids = $wpdb->get_col($wpdb->prepare("SELECT id FROM {$wpdb->prefix}hireflow_queue WHERE sent_at IS NULL AND attempts < %d ORDER BY id LIMIT 50", self::MAX_ATTEMPTS));
        foreach ($ids as $id) self::deliver((int)$id);
    }

    private static function deliver($id) {
        global $wpdb;
        $t = "{$wpdb->prefix}hireflow_queue";
        $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM $t WHERE id = %d", $id));
        if (!$row || $row->sent_at) return;
        $ts = time();
        $sig = hash_hmac('sha256', $ts . '.' . $row->payload, self::opt('secret', ''));
        $res = wp_remote_post(rtrim(self::opt('endpoint', ''), '/') . '/api/webhooks/wordpress', [
            'timeout' => 5,
            'headers' => ['Content-Type' => 'application/json', 'X-HireFlow-Timestamp' => $ts, 'X-HireFlow-Signature' => $sig],
            'body'    => $row->payload,
        ]);
        $code = is_wp_error($res) ? 0 : wp_remote_retrieve_response_code($res);
        if ($code >= 200 && $code < 300) {
            $wpdb->update($t, ['sent_at' => current_time('mysql', true), 'last_error' => null], ['id' => $id]);
        } else {
            $err = is_wp_error($res) ? $res->get_error_message() : "HTTP $code " . substr(wp_remote_retrieve_body($res), 0, 300);
            // 422 = invalid payload: stop retrying, keep for manual review
            $wpdb->query($wpdb->prepare("UPDATE $t SET attempts = %d, last_error = %s WHERE id = %d", $code === 422 ? self::MAX_ATTEMPTS : $row->attempts + 1, $err, $id));
        }
    }

    /* ---------- admin ---------- */
    private static function opt($k, $d) { $o = get_option(self::OPT, []); return isset($o[$k]) && $o[$k] !== '' ? $o[$k] : $d; }

    public static function register_settings() { register_setting('hireflow', self::OPT, ['sanitize_callback' => function ($v) { return array_map('sanitize_text_field', (array)$v); }]); }

    public static function menu() {
        add_options_page('HireFlow Connector', 'HireFlow', 'manage_options', 'hireflow', [__CLASS__, 'page']);
    }

    public static function page() {
        global $wpdb;
        $t = "{$wpdb->prefix}hireflow_queue";
        $pending = (int)$wpdb->get_var("SELECT COUNT(*) FROM $t WHERE sent_at IS NULL");
        $fields = ['endpoint' => 'Platform URL (e.g. https://hr.example.com)', 'secret' => 'Webhook secret',
                   'form_ids' => 'Form IDs to forward (comma separated, blank = all)', 'map_email' => 'Email field names (a|b)',
                   'map_name' => 'Name field names', 'map_phone' => 'Phone field names', 'map_position' => 'Position field names'];
        echo '<div class="wrap"><h1>HireFlow Connector</h1><p>Queued (not yet delivered): <strong>' . esc_html($pending) . '</strong></p><form method="post" action="options.php">';
        settings_fields('hireflow');
        echo '<table class="form-table">';
        foreach ($fields as $k => $label) {
            $type = $k === 'secret' ? 'password' : 'text';
            printf('<tr><th>%s</th><td><input class="regular-text" type="%s" name="%s[%s]" value="%s"></td></tr>', esc_html($label), $type, self::OPT, $k, esc_attr(self::opt($k, '')));
        }
        echo '</table>';
        submit_button();
        echo '</form></div>';
    }
}

HireFlow_Connector::init();
