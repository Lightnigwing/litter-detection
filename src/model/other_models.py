class ResNet50UNet(nn.Module):
    """
    U-Net with a pretrained ResNet50 encoder.
    Included for experimentation; not used by default.
    """

    def __init__(self, dropout: float = DROPOUT):
        super().__init__()
        backbone = tv_models.resnet50(weights=tv_models.ResNet50_Weights.IMAGENET1K_V2)

        self.stem_conv = nn.Sequential(backbone.conv1, backbone.bn1, backbone.relu)
        self.stem_pool = backbone.maxpool
        self.layer1 = backbone.layer1
        self.layer2 = backbone.layer2
        self.layer3 = backbone.layer3
        self.layer4 = backbone.layer4

        if FREEZE_ENCODER_BN:
            self.stem_conv.apply(freeze_encoder_batchnorm)
            self.layer1.apply(freeze_encoder_batchnorm)
            self.layer2.apply(freeze_encoder_batchnorm)
            self.layer3.apply(freeze_encoder_batchnorm)
            self.layer4.apply(freeze_encoder_batchnorm)

        self.up1 = nn.ConvTranspose2d(2048, 512, kernel_size=2, stride=2)
        self.dec1 = ConvBlock(512 + 1024, 512, dropout)

        self.up2 = nn.ConvTranspose2d(512, 256, kernel_size=2, stride=2)
        self.dec2 = ConvBlock(256 + 512, 256, dropout)

        self.up3 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.dec3 = ConvBlock(128 + 256, 128, dropout)

        self.up4 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.dec4 = ConvBlock(64 + 64, 64, dropout)

        self.final_up = nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2)
        self.final_conv = ConvBlock(32, 32, dropout)
        self.head = nn.Conv2d(32, 1, kernel_size=1)

    def _align(self, x, ref):
        if x.shape[2:] != ref.shape[2:]:
            x = F.interpolate(x, size=ref.shape[2:], mode="bilinear", align_corners=False)
        return x

    def forward(self, x):
        s0 = self.stem_conv(x)
        s1 = self.layer1(self.stem_pool(s0))
        s2 = self.layer2(s1)
        s3 = self.layer3(s2)
        s4 = self.layer4(s3)

        d = self.up1(s4)
        d = self._align(d, s3)
        d = self.dec1(torch.cat([d, s3], dim=1))

        d = self.up2(d)
        d = self._align(d, s2)
        d = self.dec2(torch.cat([d, s2], dim=1))

        d = self.up3(d)
        d = self._align(d, s1)
        d = self.dec3(torch.cat([d, s1], dim=1))

        d = self.up4(d)
        d = self._align(d, s0)
        d = self.dec4(torch.cat([d, s0], dim=1))

        d = self.final_up(d)
        d = self.final_conv(d)
        return self.head(d)


class EfficientNetB3UNet(nn.Module):
    """U-Net with a pretrained EfficientNet-B3 encoder."""

    def __init__(self, dropout: float = DROPOUT):
        super().__init__()
        backbone = tv_models.efficientnet_b3(weights=tv_models.EfficientNet_B3_Weights.IMAGENET1K_V1)
        features = backbone.features

        self.stage0 = features[0]
        self.stage1 = features[1]
        self.stage2 = features[2]
        self.stage3 = features[3]
        self.stage4 = features[4]
        self.stage5 = features[5]
        self.stage6 = features[6]
        self.stage7 = features[7]

        if FREEZE_ENCODER_BN:
            self.stage0.apply(freeze_encoder_batchnorm)
            self.stage1.apply(freeze_encoder_batchnorm)
            self.stage2.apply(freeze_encoder_batchnorm)
            self.stage3.apply(freeze_encoder_batchnorm)
            self.stage4.apply(freeze_encoder_batchnorm)
            self.stage5.apply(freeze_encoder_batchnorm)
            self.stage6.apply(freeze_encoder_batchnorm)
            self.stage7.apply(freeze_encoder_batchnorm)

        self.up1 = nn.ConvTranspose2d(384, 136, kernel_size=2, stride=2)
        self.dec1 = ConvBlock(136 + 136, 256, dropout)

        self.up2 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.dec2 = ConvBlock(128 + 48, 128, dropout)

        self.up3 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.dec3 = ConvBlock(64 + 32, 64, dropout)

        self.up4 = nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2)
        self.dec4 = ConvBlock(32 + 24, 32, dropout)

        self.final_up = nn.ConvTranspose2d(32, 16, kernel_size=2, stride=2)
        self.final_conv = ConvBlock(16, 16, dropout)
        self.head = nn.Conv2d(16, 1, kernel_size=1)

    def _align(self, x, ref):
        if x.shape[2:] != ref.shape[2:]:
            x = F.interpolate(x, size=ref.shape[2:], mode="bilinear", align_corners=False)
        return x

    def forward(self, x):
        s0 = self.stage0(x)
        s1 = self.stage1(s0)
        s2 = self.stage2(s1)
        s3 = self.stage3(s2)
        s4 = self.stage4(s3)
        s5 = self.stage5(s4)
        s6 = self.stage6(s5)
        s7 = self.stage7(s6)

        d = self.up1(s7)
        d = self._align(d, s5)
        d = self.dec1(torch.cat([d, s5], dim=1))

        d = self.up2(d)
        d = self._align(d, s3)
        d = self.dec2(torch.cat([d, s3], dim=1))

        d = self.up3(d)
        d = self._align(d, s2)
        d = self.dec3(torch.cat([d, s2], dim=1))

        d = self.up4(d)
        d = self._align(d, s1)
        d = self.dec4(torch.cat([d, s1], dim=1))

        d = self.final_up(d)
        d = self.final_conv(d)
        return self.head(d)


class EfficientNetB4UNet(nn.Module):
    """U-Net with a pretrained EfficientNet-B4 encoder."""

    def __init__(self, dropout: float = DROPOUT):
        super().__init__()
        backbone = tv_models.efficientnet_b4(weights=tv_models.EfficientNet_B4_Weights.IMAGENET1K_V1)
        features = backbone.features

        self.stage0 = features[0]
        self.stage1 = features[1]
        self.stage2 = features[2]
        self.stage3 = features[3]
        self.stage4 = features[4]
        self.stage5 = features[5]
        self.stage6 = features[6]
        self.stage7 = features[7]

        if FREEZE_ENCODER_BN:
            for m in [self.stage0, self.stage1, self.stage2, self.stage3, self.stage4, self.stage5, self.stage6, self.stage7]:
                m.apply(freeze_encoder_batchnorm)

        self.up1 = nn.ConvTranspose2d(448, 160, kernel_size=2, stride=2)
        self.dec1 = ConvBlock(160 + 160, 256, dropout)

        self.up2 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.dec2 = ConvBlock(128 + 56, 128, dropout)

        self.up3 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.dec3 = ConvBlock(64 + 32, 64, dropout)

        self.up4 = nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2)
        self.dec4 = ConvBlock(32 + 24, 32, dropout)

        self.final_up = nn.ConvTranspose2d(32, 16, kernel_size=2, stride=2)
        self.final_conv = ConvBlock(16, 16, dropout)
        self.head = nn.Conv2d(16, 1, kernel_size=1)

    def _align(self, x, ref):
        if x.shape[2:] != ref.shape[2:]:
            x = F.interpolate(x, size=ref.shape[2:], mode="bilinear", align_corners=False)
        return x

    def forward(self, x):
        s0 = self.stage0(x)
        s1 = self.stage1(s0)
        s2 = self.stage2(s1)
        s3 = self.stage3(s2)
        s4 = self.stage4(s3)
        s5 = self.stage5(s4)
        s6 = self.stage6(s5)
        s7 = self.stage7(s6)

        d = self.up1(s7)
        d = self._align(d, s5)
        d = self.dec1(torch.cat([d, s5], dim=1))

        d = self.up2(d)
        d = self._align(d, s3)
        d = self.dec2(torch.cat([d, s3], dim=1))

        d = self.up3(d)
        d = self._align(d, s2)
        d = self.dec3(torch.cat([d, s2], dim=1))

        d = self.up4(d)
        d = self._align(d, s1)
        d = self.dec4(torch.cat([d, s1], dim=1))

        d = self.final_up(d)
        d = self.final_conv(d)
        return self.head(d)
    
class UNet(nn.Module):
    """
    Vanilla U-Net for binary segmentation.
    Encoder depth and channel widths are controlled by ENCODER_CHANNELS /
    DECODER_CHANNELS — the agent is free to change these.
    """
    def __init__(
        self,
        in_channels: int = 3,
        encoder_channels: list[int] = ENCODER_CHANNELS,
        decoder_channels: list[int] = DECODER_CHANNELS,
        dropout: float = DROPOUT,
    ):
        super().__init__()
        assert len(encoder_channels) == len(decoder_channels)

        self.encoders = nn.ModuleList()
        self.pools = nn.ModuleList()
        ch = in_channels
        for out_ch in encoder_channels:
            self.encoders.append(ConvBlock(ch, out_ch, dropout))
            self.pools.append(nn.MaxPool2d(2))
            ch = out_ch

        self.bottleneck = ConvBlock(ch, ch * 2, dropout)
        ch = ch * 2

        self.upconvs = nn.ModuleList()
        self.decoders = nn.ModuleList()
        for enc_ch, dec_ch in zip(reversed(encoder_channels), decoder_channels):
            self.upconvs.append(nn.ConvTranspose2d(ch, enc_ch, kernel_size=2, stride=2))
            self.decoders.append(ConvBlock(enc_ch * 2, dec_ch, dropout))
            ch = dec_ch

        self.head = nn.Conv2d(ch, 1, kernel_size=1)

    def forward(self, x):
        skips = []
        for enc, pool in zip(self.encoders, self.pools):
            x = enc(x)
            skips.append(x)
            x = pool(x)

        x = self.bottleneck(x)

        for upconv, dec, skip in zip(self.upconvs, self.decoders, reversed(skips)):
            x = upconv(x)
            if x.shape != skip.shape:
                x = F.interpolate(x, size=skip.shape[2:], mode="bilinear", align_corners=False)
            x = torch.cat([skip, x], dim=1)
            x = dec(x)

        return self.head(x)