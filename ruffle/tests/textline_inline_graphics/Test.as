package {
    import flash.display.BitmapData;
    import flash.display.Sprite;
    import flash.geom.Matrix;
    import flash.events.Event;
    import flash.text.engine.*;

    public class Test extends Sprite {
        public function Test() {
            var red:Sprite = box(0xff0000, 10, 8);
            var format:ElementFormat = new ElementFormat(null, 20, 0xffffff);
            var graphic:GraphicElement = new GraphicElement(red, 25, 35, format);
            trace("constructor", graphic.graphic === red && graphic.elementWidth === 25 && graphic.elementHeight === 35);
            var group:GroupElement = new GroupElement(new <ContentElement>[
                new TextElement("a", format), graphic, new TextElement("a", format)
            ]);
            var block:TextBlock = new TextBlock(group);
            var line:TextLine = block.createTextLine(null, 400);
            var plain:TextLine = new TextBlock(new TextElement("aa", format)).createTextLine(null, 400);
            trace("raw", group.text === "aa" && group.rawText === "a" + String.AS3::fromCharCode(ContentElement.GRAPHIC_ELEMENT) + "a" && line.rawTextLength === 3);
            var holder:Sprite = red.parent as Sprite;
            trace("child", holder.parent === line && line.numChildren === 1 && line.getChildAt(0) === holder && line.hasGraphicElement);
            trace("layout", line.textWidth >= plain.textWidth + 24.9 && line.ascent >= 35);
            trace("unscaled", red.width === 10 && red.height === 8);
            trace("render", containsColor(line, 0xff0000));
            var removed:int = 0;
            red.addEventListener(Event.REMOVED, function(event:Event):void { removed++; });
            graphic.graphic = red;
            trace("same", red.parent === holder && holder.parent === line && line.numChildren === 1 && removed === 0);
            var blue:Sprite = box(0x0000ff, 6, 6);
            var x:Number = red.x, y:Number = red.y;
            graphic.graphic = blue;
            trace("replace", red.parent === null && blue.parent === holder && holder.parent === line && line.numChildren === 1 && blue.x === x && blue.y === y);
            trace("replacement pixels", !containsColor(line, 0xff0000) && containsColor(line, 0x0000ff));
            graphic.graphic = null;
            trace("null", blue.parent === null && holder.numChildren === 0 && line.numChildren === 1 && line.hasGraphicElement);
            graphic.graphic = red;
            graphic.elementWidth = 40;
            graphic.elementHeight = 45;
            block.recreateTextLine(line, null, 400);
            trace("resize", graphic.elementWidth === 40 && graphic.elementHeight === 45 && line.textWidth >= plain.textWidth + 39.9 && line.ascent >= 45 && red.width === 10 && red.height === 8);
            block.content = new TextElement("plain", format);
            block.recreateTextLine(line, null, 400);
            trace("recreate", red.parent === holder && holder.parent === null && line.numChildren === 0 && !line.hasGraphicElement);
            graphic.graphic = blue;
            trace("detached", blue.parent === holder && holder.parent === null && red.parent === null);
            var nested:TextBlock = new TextBlock(new GroupElement(new <ContentElement>[
                new TextElement("a" + String.AS3::fromCharCode(0xd83d, 0xde00) + "\n", format), new GroupElement(new <ContentElement>[graphic])
            ]));
            var first:TextLine = nested.createTextLine(null, 400);
            var second:TextLine = nested.createTextLine(first, 400);
            trace("continuation", !first.hasGraphicElement && second.hasGraphicElement && blue.parent.parent === second && second.textBlockBeginIndex === 4 && second.rawTextLength === 1);
            var green:Sprite = box(0x00ff00, 8, 8);
            var pair:TextBlock = new TextBlock(new GroupElement(new <ContentElement>[graphic, new GraphicElement(green, 25, 35, format)]));
            var pairLine:TextLine = pair.createTextLine(null, 400);
            trace("adjacent", pairLine.rawTextLength === 2 && pairLine.numChildren === 2 && pairLine.getChildAt(0) === blue.parent && pairLine.getChildAt(1) === green.parent && green.parent.x >= blue.parent.x + 40);
        }
        private function box(color:uint, width:Number, height:Number):Sprite {
            var result:Sprite = new Sprite();
            result.graphics.beginFill(color);
            result.graphics.drawRect(0, 0, width, height);
            result.graphics.endFill();
            return result;
        }
        private function containsColor(line:TextLine, color:uint):Boolean {
            var image:BitmapData = new BitmapData(160, 80, false, 0);
            image.draw(line, new Matrix(1, 0, 0, 1, 4, 50));
            var found:Boolean = false;
            for (var y:int = 0; y < image.height; y++) {
                for (var x:int = 0; x < image.width; x++) found = found || image.getPixel(x, y) === color;
            }
            image.dispose();
            return found;
        }
    }
}
