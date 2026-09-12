/**
 * Script-free HTML export guard (I10/I09).
 *
 * The human report is a self-contained `.html` with no JavaScript, no
 * forms, no external resources and a meta-CSP locked to
 * `default-src 'none'` plus `img-src data:` for the embedded sanitized
 * PNGs. This module verifies that invariant on the *serialized* export
 * bytes: any active element, event-handler attribute, dangerous URL
 * scheme, external reference or missing CSP fails with
 * ContractError('HTML'). It is the tripwire every exporter — the T16
 * product exporter and the test double alike — must pass before output
 * is considered openable.
 *
 * Also provided: `escapeHtml`, the single escaping rule (text nodes and
 * quoted attributes) the exporter contract relies on. Imported report
 * strings must never reach HTML output unescaped.
 */
import { ContractError, sha256 } from '../../contracts/src/index.ts';
import { decodeBase64 } from './assets.ts';
import { decodePng } from './png.ts';

function fail(message: string): never {
  throw new ContractError('HTML', message);
}

/** Escape text/attribute content; equivalent semantics to html.escape(s, quote=True). */
export function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#x27;');
}

/** Elements that are never allowed in a script-free report. */
const FORBIDDEN_ELEMENTS = [
  'script', 'iframe', 'object', 'embed', 'applet', 'form', 'input',
  'button', 'select', 'textarea', 'option', 'fieldset', 'a', 'area',
  'link', 'base', 'meta-refresh', 'video', 'audio', 'source', 'track',
  'picture', 'svg', 'math', 'template', 'slot', 'noscript', 'frameset',
  'frame', 'portal', 'param', 'isindex', 'keygen', 'dialog',
] as const;

/** Attributes that can trigger loads, scripts or navigation. */
const FORBIDDEN_ATTRS = [
  'srcdoc', 'srcset', 'formaction', 'xlink:href', 'data', 'action',
  'background', 'poster', 'href', 'style', 'ping', 'manifest',
  'content', // guarded separately on <meta http-equiv>
] as const;

/** URI schemes that must never appear inside a markup attribute. */
const FORBIDDEN_SCHEMES = ['javascript:', 'vbscript:', 'data:'];

/** URL-ish constructs that must never appear inside the fixed stylesheet. */
const FORBIDDEN_CSS = [
  'url(', '@import', 'expression(', 'behavior:', '-moz-binding',
  '@charset', 'javascript:', 'vbscript:',
] as const;

/**
 * Decode HTML entities inside an attribute value. Exporters escape `'` and
 * `"` (and an attacker would reach for `&#x…;` to smuggle a scheme), so
 * every value is normalized to its decoded form before any check runs.
 */
function decodeEntities(value: string): string {
  const named: Record<string, string> = {
    amp: '&',
    lt: '<',
    gt: '>',
    quot: '"',
    apos: "'",
    colon: ':',
    sol: '/',
    equals: '=',
    Tab: '\t',
    NewLine: '\n',
  };
  return value.replace(
    /&(#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[a-zA-Z]+);?/g,
    (whole, body: string) => {
      if (body.startsWith('#x') || body.startsWith('#X')) {
        const cp = parseInt(body.slice(2), 16);
        return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : whole;
      }
      if (body.startsWith('#')) {
        const cp = parseInt(body.slice(1), 10);
        return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : whole;
      }
      return Object.prototype.hasOwnProperty.call(named, body)
        ? named[body]!
        : whole;
    },
  );
}

const TAG_RE = /<\s*\/?\s*([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>/g;
const PREAMBLE_RE = /^\s*(?:<!doctype html\s*>\s*|<(?:html|head|meta)(?=\s|>)(?:"[^"]*"|'[^']*'|[^>"'])*>\s*)*$/i;
const META_CSP_RE = /<meta\s[^>]*http-equiv\s*=\s*["']?Content-Security-Policy["']?[^>]*>/i;
const REQUIRED_CSP = ['default-src', 'img-src', 'base-uri', 'form-action', 'style-src'];
const CSP_VALUES: Record<string, string> = {
  'default-src': "'none'", 'img-src': 'data:', 'base-uri': "'none'",
  'form-action': "'none'", 'script-src': "'none'", 'connect-src': "'none'",
  'object-src': "'none'", 'frame-src': "'none'", 'child-src': "'none'",
  'worker-src': "'none'", 'font-src': "'none'", 'media-src': "'none'",
};

/** Owned HTML uses quoted attribute values; duplicates fail instead of guessing. */
function attributes(text: string): Map<string, string> {
  const result = new Map<string, string>();
  const source = text.trimEnd().replace(/\/$/, '').trimEnd();
  const re = /\s+([a-zA-Z_:][a-zA-Z0-9_.:-]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'))?/gy;
  while (re.lastIndex < source.length) {
    const match = re.exec(source);
    if (match === null) fail('Malformed or unquoted attribute');
    const name = match[1]!.toLowerCase();
    if (result.has(name)) fail(`Duplicate attribute ${name}`);
    result.set(name, match[2] ?? match[3] ?? '');
  }
  return result;
}

/** Source lists are exact tokens; another directive may not override a default. */
function policyStyleHash(content: string): string {
  const directives = new Map<string, string>();
  for (const part of decodeEntities(content).split(';')) {
    const [rawName, ...sources] = part.trim().split(/[\t\n\f\r ]+/);
    if (!rawName) continue;
    const name = rawName.toLowerCase();
    if (directives.has(name)) fail(`Duplicate CSP directive ${name}`);
    const value = sources.join(' ');
    const hash = name === 'style-src' && /^'sha256-[A-Za-z0-9+/]{43}='$/.test(value);
    if (value !== CSP_VALUES[name] && !hash) fail(`Forbidden CSP source list ${name}`);
    directives.set(name, value);
  }
  for (const name of REQUIRED_CSP) {
    if (!directives.has(name)) fail(`Missing CSP directive ${name}`);
  }
  return directives.get('style-src')!;
}

function requiredCsp(html: string): string {
  const match = META_CSP_RE.exec(html);
  if (match === null) fail('Missing Content-Security-Policy meta');
  if (!PREAMBLE_RE.test(html.slice(0, match.index))) fail('CSP must precede document content');
  const tag = Array.from(match[0].matchAll(TAG_RE))[0];
  if (tag === undefined) fail('Malformed CSP meta');
  const attrs = attributes(tag[2]!);
  if (attrs.get('http-equiv')?.toLowerCase() !== 'content-security-policy') fail('Malformed CSP meta');
  const content = attrs.get('content');
  if (content === undefined) fail('CSP meta lacks content attribute');
  return policyStyleHash(content);
}

/** Decode the actual image; a MIME prefix or a PNG signature is insufficient. */
function embeddedPng(value: string): void {
  const match = /^data:image\/png;base64,([A-Za-z0-9+/]*={0,2})$/.exec(value);
  if (match === null) fail('src attribute is not a strict embedded PNG data URL');
  try {
    decodePng(decodeBase64(match[1]!));
  } catch (error) {
    if (error instanceof ContractError) fail('Invalid embedded PNG');
    throw error;
  }
}

function assertAttributeValue(element: string, name: string, rawValue: string): void {
  const value = decodeEntities(rawValue).trim();
  const lower = value.toLowerCase();
  if (name === 'src') {
    if (element !== 'img') fail('Only img may have src');
    embeddedPng(value);
    return;
  }
  for (const scheme of FORBIDDEN_SCHEMES) {
    if (scheme === 'data:' && name === 'content') continue;
    if (lower.includes(scheme)) fail(`Forbidden scheme ${scheme} in attribute ${name}`);
  }
  if (name === 'http-equiv' && lower !== 'content-security-policy') {
    fail(`Forbidden meta http-equiv ${value}`);
  }
}

function assertAttributes(element: string, attrs: Map<string, string>): void {
  for (const [name, rawValue] of attrs) {
    if (name.startsWith('on')) fail(`Event-handler attribute ${name}`);
    if (name !== 'content' && (FORBIDDEN_ATTRS as readonly string[]).includes(name)) {
      fail(`Forbidden attribute ${name}`);
    }
    assertAttributeValue(element, name, rawValue);
  }
}

/** Conservative lexical tripwire after CSS escape decoding/comment removal. */
function cssForInspection(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\\([0-9a-fA-F]{1,6})(?:\r\n|[\t\n\f\r ])?|\\([^\n\r\f])/g,
      (_match, hex: string | undefined, char: string | undefined) => {
        if (hex === undefined) return char!;
        const point = parseInt(hex, 16);
        if (point === 0 || point > 0x10ffff) return '\ufffd';
        return String.fromCodePoint(point);
      })
    .toLowerCase();
}

function assertStyles(html: string, hash: string): void {
  const re = /<style(?=\s|>)[^>]*>([\s\S]*?)(<\/style\s*>|$)/gi;
  for (const match of html.matchAll(re)) {
    if (!match[2]) fail('Unclosed stylesheet');
    const css = match[1]!;
    const actual = "'sha256-" + btoa(String.fromCharCode(...sha256(new TextEncoder().encode(css)))) + "'";
    if (actual !== hash) fail('Stylesheet does not match its CSP hash');
    const inspected = cssForInspection(css);
    for (const token of FORBIDDEN_CSS) {
      if (inspected.includes(token)) fail(`Forbidden stylesheet construct ${token}`);
    }
  }
}

/**
 * Verify owned serialized report HTML. This conservative grammar requires an
 * early real CSP meta, quoted attributes and hash-bound styles; it is not an
 * arbitrary HTML sanitizer. Imported markup must never reach the document.
 */
export function assertScriptFreeHtml(html: string): void {
  if (html.includes('\u0000')) fail('NUL byte in export');
  // Comments/processing instructions are absent from owned templates. Reject
  // them rather than confusing inert text with active markup during scanning.
  if (/<!--|<!\[endif|<\?/i.test(html)) fail('Comment or processing instruction in export');
  const hash = requiredCsp(html);
  for (const match of html.matchAll(TAG_RE)) {
    const element = match[1]!.toLowerCase();
    if ((FORBIDDEN_ELEMENTS as readonly string[]).includes(element)) fail(`Forbidden element <${element}>`);
    assertAttributes(element, attributes(match[2]!));
  }
  assertStyles(html, hash);
}
