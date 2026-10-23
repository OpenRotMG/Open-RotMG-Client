package {
    import flash.display.BitmapData;
    import flash.display.Sprite;
    import flash.text.engine.*;

    public class Test extends Sprite {
        public function Test() {
            var green:ElementFormat = new ElementFormat(null, 20, 0x00ff00);
            var white:ElementFormat = new ElementFormat(null, 20, 0xffffff);
            var cyan:ElementFormat = new ElementFormat(null, 20, 0x00f0ff);
            var yellow:ElementFormat = new ElementFormat(null, 20, 0xffff00);
            check("chat", new GroupElement(new <ContentElement>[
                new TextElement("<Player> ", green), new TextElement("Message", white)
            ]), [0x00ff00, 0xffffff]);
            check("nested", new GroupElement(new <ContentElement>[
                new TextElement("To: ", white), new GroupElement(new <ContentElement>[
                    new TextElement("<Player> ", green), new TextElement("Message", cyan)
                ], yellow)
            ]), [0xffffff, 0x00ff00, 0x00f0ff]);
            check("continuation", new GroupElement(new <ContentElement>[
                new TextElement("<Player> \n", green), new TextElement("Message", white)
            ]), [0x00ff00, 0xffffff]);
            check("unicode", new GroupElement(new <ContentElement>[
                new TextElement("<\ud83d\ude00Player> ", green), new TextElement("Message", white)
            ]), [0x00ff00, 0xffffff]);
            check("single", new TextElement("Server", yellow), [0xffff00]);
        }

        private function check(label:String, content:ContentElement, colors:Array):void {
            var sprite:Sprite = new Sprite();
            var block:TextBlock = new TextBlock(content);
            var line:TextLine = null;
            var y:Number = 0;
            while ((line = block.createTextLine(line, 500)) != null) {
                line.x = 2;
                y += line.ascent + line.descent + 4;
                line.y = y;
                sprite.addChild(line);
            }
            var image:BitmapData = new BitmapData(520, 100, false, 0);
            image.draw(sprite);
            var present:Object = {};
            for (var row:int = 0; row < image.height; row++) {
                for (var col:int = 0; col < image.width; col++) present[image.getPixel(col, row)] = true;
            }
            for each (var color:uint in colors) trace(label, color.toString(16), present[color] === true);
            image.dispose();
        }
    }
}
