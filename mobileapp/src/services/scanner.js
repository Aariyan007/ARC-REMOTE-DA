/**
 * QR scanning for pairing (native only). Returns the raw QR text, or null if cancelled.
 */
import { BarcodeScanner, BarcodeFormat } from '@capacitor-mlkit/barcode-scanning';
import { isNative, platformName } from '../utils/platform.js';

export async function scanPairingQr() {
  if (!isNative()) throw new Error('QR scanning is only available in the mobile app.');

  const { supported } = await BarcodeScanner.isSupported();
  if (!supported) throw new Error('This device cannot scan QR codes. Enter the details manually.');

  const perm = await BarcodeScanner.requestPermissions();
  if (perm.camera !== 'granted' && perm.camera !== 'limited') {
    throw new Error('Camera permission is needed to scan. Enable it in Settings or enter the details manually.');
  }

  if (platformName() === 'android') {
    const { available } = await BarcodeScanner.isGoogleBarcodeScannerModuleAvailable();
    if (!available) await BarcodeScanner.installGoogleBarcodeScannerModule();
  }

  const { barcodes } = await BarcodeScanner.scan({ formats: [BarcodeFormat.QrCode] });
  return barcodes?.[0]?.rawValue || null;
}
